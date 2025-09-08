# /opt/pontua/AutoPonto/backend_api/extractor_jbs.py

import os
import tempfile
import pandas as pd
from io import BytesIO
import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import re
from datetime import datetime
import time
from rq import get_current_job # <--- IMPORTAÇÃO NECESSÁRIA PARA OBTER O OBJETO JOB

# --- AJUSTE 1: Caminho do Tesseract para Linux ---
import platform
if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
# -------------------------------------------------

class ExtractorPontoEletronico:
    def __init__(self, model_type='1', job=None):
        self.model_type = model_type
        self.config_ocr = r'--oem 3 --psm 6 -l por'
        self.job = job # Armazena o objeto job do RQ

    def update_progress(self, current_step, total_steps, message, status='processing'):
        """Atualiza o progresso da tarefa usando o objeto job do RQ."""
        if self.job:
            effective_total_steps = total_steps if total_steps > 0 else 1
            progress_percent = int((current_step / effective_total_steps) * 100)
            
            self.job.meta['progress'] = progress_percent
            self.job.meta['message'] = message
            self.job.meta['current_step'] = current_step
            self.job.meta['total_steps'] = total_steps
            self.job.meta['status'] = status
            self.job.meta['timestamp'] = datetime.now().isoformat()
            self.job.save() # Salva o meta no Redis
            print(f"[RQ Job {self.job.id}] Progress: {progress_percent}% - {message}") # Para debug no worker

    def converter_pdf_imagens(self, pdf_path, pages_range=None, dpi=300):
        """Converte PDF para imagens"""
        try:
            if pages_range:
                if '-' in pages_range:
                    start, end = map(int, pages_range.split('-'))
                    first_page = start
                    last_page = end
                else:
                    first_page = last_page = int(pages_range)
                imagens = convert_from_path(
                    pdf_path,
                    dpi=dpi,
                    first_page=first_page,
                    last_page=last_page
                )
            else:
                imagens = convert_from_path(pdf_path, dpi=dpi)
            return imagens
        except Exception as e:
            print(f"Erro ao converter PDF para imagens: {e}")
            if self.job:
                self.job.meta['error'] = f"Erro ao converter PDF: {str(e)}"
                self.job.meta['status'] = 'error'
                self.job.save()
            return []

    def extrair_texto_completo(self, imagem):
        """Extrai todo o texto da página usando OCR"""
        try:
            img_cv = cv2.cvtColor(np.array(imagem), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            gray = cv2.bilateralFilter(gray, 9, 75, 75)
            return pytesseract.image_to_string(gray, config=self.config_ocr)
        except Exception as e:
            print(f"Erro ao extrair texto com OCR: {e}")
            return ""

    def detectar_inicio_tabela(self, linhas):
        """Detecta onde a tabela de ponto começa"""
        for i, linha in enumerate(linhas):
            if re.search(r'\b(Dia|Data)\b', linha) and re.search(r'\b(Marcação|Situação)\b', linha):
                return i
        return 0

    def detectar_fim_tabela(self, linhas, indice_inicio):
        """Detecta onde a tabela de ponto termina"""
        for i in range(indice_inicio, len(linhas)):
            linha = linhas[i].strip()
            if not linha:
                return i
            if re.search(r'\b(assinatura|funcionário|chefia|visto|total|observações)\b', linha, re.IGNORECASE):
                return i
        return len(linhas)

    def validar_horarios(self, horarios_validos):
        """
        Valida os horários seguindo as regras:
        1. Se apenas 1 horário, zerar todos
        2. Se tiver entrada sem saída correspondente, zerar ambos
        3. Se tiver saída sem entrada correspondente, zerar a saída
        """
        while len(horarios_validos) < 4:
            horarios_validos.append("0")
        horarios_validos = horarios_validos[:4]

        horarios_nao_zero = [h for h in horarios_validos if h != "0"]

        if len(horarios_nao_zero) == 1:
            return ["0", "0", "0", "0"]

        entrada1, saida1, entrada2, saida2 = horarios_validos

        if entrada1 != "0" and saida1 == "0":
            entrada1 = "0"
            saida1 = "0"
        if entrada1 == "0" and saida1 != "0":
            saida1 = "0"
        if entrada2 != "0" and saida2 == "0":
            entrada2 = "0"
            saida2 = "0"
        if entrada2 == "0" and saida2 != "0":
            saida2 = "0"
        return [entrada1, saida1, entrada2, saida2]

    def processar_texto_ponto(self, texto):
        """Processa o texto extraído para encontrar dados de ponto"""
        linhas = texto.split('\n')
        indice_inicio = self.detectar_inicio_tabela(linhas)
        indice_fim = self.detectar_fim_tabela(linhas, indice_inicio)
        linhas_tabela = linhas[indice_inicio:indice_fim]

        colunas_proibidas = [
            'Marcação ou', 'MARCAÇÃO OU', 'marcação ou',
            'FALTAS', 'FALTA', 'Faltas', 'Falta', 'faltas', 'falta',
            'AD.NOT', 'AD NOT', 'ADNOT', 'ad.not', 'ad not', 'adnot',
            'H.E.100%', 'H E 100%', 'HE 100%', 'h.e.100%', 'he100%',
            'H.E.NEG', 'H E NEG', 'HE NEG', 'h.e.neg', 'heneg',
            'FALTS', 'FALT', 'FAULT', 'FAULTS',
            'A.NOT', 'ANOT', 'AD-NOT', 'ADNOT.',
            'H.E100%', 'HE.100%', 'HE100%', 'H.E.100', 'HE.100',
            'H.E50%', 'HE.50%', 'HE50%', 'H.E.50', 'HE.50',
            'H.NEG', 'HNEG', 'H NEG', 'H-NEG', 'H.N', 'HN', 'NEG',
            'C.DIA', 'CDIA', 'C DIA', 'C-DIA', 'C.D', 'CD', 'COMP.DIA',
            'S.POS', 'SPOS', 'S POS', 'S-POS', 'S.P', 'SP', 'POS',
            'S.NEG', 'SNEG', 'S NEG', 'S-NEG', 'S.N', 'SN',
            'H.SUP', 'HSUP', 'H SUP', 'H-SUP', 'H.S', 'HS', 'SUP',
            'SALDO', 'SALD', 'SAL', 'TOTAL', 'TOT',
            'VISTO', 'CHEFIA', 'ASSINATURA', 'FUNCIONARIO', 'FUNCIONÁRIO',
            'ATESTADO', 'MEDICO', 'MÉDICO', 'LICENÇA', 'LICENCA',
            'FALTA JUSTIFICADA', 'FALTA ABONADA', 'FÉRIAS', 'FERIAS'
        ]
        dados_extraidos = []
        dias_semana = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom']
        for linha in linhas_tabela:
            linha = linha.strip()
            if not linha:
                continue
            data_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', linha)
            if data_match:
                data = data_match.group(1)
                dia_semana = ""
                for dia in dias_semana:
                    if dia in linha:
                        dia_semana = dia
                        break
                if not dia_semana:
                    if any(variacao in linha for variacao in ['Sáb', 'SAB', 'sab', 'Sabado', 'sábado']):
                        dia_semana = 'Sab'
                pos_data = linha.find(data)
                inicio_busca = pos_data + len(data)
                if dia_semana and dia_semana in linha:
                    pos_dia = linha.find(dia_semana)
                    if pos_dia > pos_data:
                        inicio_busca = pos_dia + len(dia_semana)
                substring_horarios = linha[inicio_busca:]
                linha_upper = substring_horarios.upper()
                pos_fim = len(substring_horarios)
                for coluna in colunas_proibidas:
                    coluna_upper = coluna.upper()
                    if coluna_upper in linha_upper:
                        pos_temp = linha_upper.find(coluna_upper)
                        if pos_temp >= 0 and pos_temp < pos_fim:
                            pos_fim = pos_temp
                            break
                parte_horarios = substring_horarios[:pos_fim]
                horarios = re.findall(r'\b([0-2]?\d:[0-5]\d)\b', parte_horarios)

                horarios_validos = []
                for h in horarios[:4]:
                    if ':' in h:
                        try:
                            horas, minutos = h.split(':')
                            horas_int = int(horas)
                            minutos_int = int(minutos)
                            if 0 <= horas_int <= 23 and 0 <= minutos_int <= 59:
                                if horas_int == 0 and minutos_int == 0:
                                    horarios_validos.append("24:00")
                                else:
                                    horarios_validos.append(f"{horas_int:02d}:{minutos_int:02d}")
                        except Exception:
                            continue
                palavras_especiais = ['FOLG', 'COMP', 'FER', 'INTEGRAÇÃO', 'INTERAÇÃO',
                                      'ATESTADO', 'MÉDICO', 'FALTA', 'LICENÇA', 'FÉRIAS']
                if any(palavra in linha.upper() for palavra in palavras_especiais):
                    horarios_validos = ["0", "0", "0", "0"]
                else:
                    horarios_validos = self.validar_horarios(horarios_validos)
                dados_linha = {
                    'Dia': data,
                    'Dia_Semana': dia_semana,
                    'Entrada1': horarios_validos[0],
                    'Saida1': horarios_validos[1],
                    'Entrada2': horarios_validos[2],
                    'Saida2': horarios_validos[3]
                }
                dados_extraidos.append(dados_linha)
        return dados_extraidos

    def processar_pagina(self, imagem, num_pagina):
        """Processa uma página completa usando OCR direto"""
        texto_completo = self.extrair_texto_completo(imagem)
        if not texto_completo:
            return pd.DataFrame()
        dados_extraidos = self.processar_texto_ponto(texto_completo)
        if dados_extraidos:
            df = pd.DataFrame(dados_extraidos)
            df['Pagina'] = num_pagina
            return df
        else:
            return pd.DataFrame()

    def processar_pdf_completo(self, pdf_path, pages_range=None):
        """Processa PDF completo"""
        self.update_progress(0, 1, "Iniciando processamento e convertendo PDF para imagens...")
        imagens = self.converter_pdf_imagens(pdf_path, pages_range)
        if not imagens:
            self.update_progress(1, 1, "Erro: Não foi possível converter o PDF ou nenhuma página encontrada.", status='error')
            return []
        
        total_paginas_reais = len(imagens)
        self.update_progress(0, total_paginas_reais, f"PDF convertido. {total_paginas_reais} páginas para processar.")
        
        todas_tabelas = []
        for i, imagem in enumerate(imagens, 1):
            self.update_progress(i, total_paginas_reais, f"Processando página {i} de {total_paginas_reais}...")
            
            if pages_range and '-' in pages_range:
                start_page = int(pages_range.split('-')[0])
                num_pagina_real = start_page + i - 1
            else:
                num_pagina_real = i
            
            df_pagina = self.processar_pagina(imagem, num_pagina_real)
            if not df_pagina.empty:
                todas_tabelas.append(df_pagina)
        
        self.update_progress(total_paginas_reais, total_paginas_reais, "Consolidando dados extraídos...")
        
        if todas_tabelas:
            df_consolidado = pd.concat(todas_tabelas, ignore_index=True)
            self.update_progress(total_paginas_reais, total_paginas_reais, "Processamento concluído com sucesso!", status='completed')
            return [df_consolidado]
        else:
            self.update_progress(total_paginas_reais, total_paginas_reais, "Nenhum dado foi extraído.", status='completed')
            return []

# Esta é a função que será enfileirada pelo RQ Worker
# A assinatura da função NÃO inclui 'job' como argumento explícito
def process_pdf_task(pdf_path, pages, model_type):
    """Função principal para ser executada pelo RQ Worker."""
    job = get_current_job() # <--- OBTÉM O OBJETO JOB AQUI DENTRO DA FUNÇÃO
    if not job:
        # Isso não deve acontecer em um contexto de worker RQ real, mas é bom para segurança
        print("Erro: Não foi possível obter o objeto job do RQ.")
        # Em um cenário real, você pode querer registrar isso de forma mais robusta
        return None

    try:
        # Agora o objeto 'job' é passado para o ExtractorPontoEletronico
        extrator = ExtractorPontoEletronico(model_type, job)
        tabelas = extrator.processar_pdf_completo(pdf_path, pages)

        if not tabelas:
            job.meta.update({
                'status': 'error',
                'error': 'Nenhuma tabela foi encontrada no PDF',
                'progress': 100,
                'message': 'Nenhuma tabela foi encontrada no PDF.'
            })
            job.save()
            return None

        final_total_steps = job.meta.get('total_steps', 1)
        extrator.update_progress(final_total_steps, final_total_steps, "Gerando arquivo CSV...", status='processing')

        output = BytesIO()
        df_final = tabelas[0]
        colunas_finais = ['Dia', 'Dia_Semana', 'Entrada1', 'Saida1', 'Entrada2', 'Saida2']
        for col in colunas_finais:
            if col not in df_final.columns:
                df_final[col] = "0"
        df_final = df_final[colunas_finais]
        df_final = df_final.fillna("0")
        df_final = df_final.replace("", "0")

        df_final.to_csv(output, index=False, encoding='utf-8', sep=';')
        output.seek(0)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'JBS_ponto_extraido_{timestamp}.csv'
        
        # Salvar o arquivo CSV em um local temporário acessível
        # O resultado do job do RQ será o caminho para este arquivo
        temp_file_path = os.path.join(tempfile.gettempdir(), f"{job.id}.csv")
        with open(temp_file_path, 'wb') as f:
            f.write(output.getvalue())

        job.meta.update({
            'status': 'completed',
            'file_path': temp_file_path,
            'filename': filename,
            'progress': 100,
            'message': 'Arquivo processado com sucesso!'
        })
        job.save()
        return temp_file_path # O resultado do job é o caminho do arquivo
    except Exception as e:
        error_message = f'Erro durante o processamento da tarefa {job.id}: {str(e)}'
        print(error_message)
        job.meta.update({
            'status': 'error',
            'error': error_message,
            'progress': 0,
            'message': error_message
        })
        job.save()
        return None
    finally:
        # Limpar o arquivo PDF temporário que foi enviado para o worker
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)


