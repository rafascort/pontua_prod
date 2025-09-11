# /opt/pontua/AutoPonto/backend_api/extractor_brf.py
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
from datetime import datetime, timedelta
from rq import get_current_job
# Caminho do Tesseract para Linux
import platform
if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

class ExtractorPontoEletronico:
    # model_type='2' é o padrão para BRF
    def __init__(self, model_type='2', job=None, debug_mode=False):
        self.model_type = model_type
        self.config_ocr = r'--oem 3 --psm 6 -l por'
        self.job = job
        self.debug_mode = debug_mode
        self.dias_semana_map = {
            'Mon': 'Seg', 'Tue': 'Ter', 'Wed': 'Qua', 'Thu': 'Qui',
            'Fri': 'Sex', 'Sat': 'Sab', 'Sun': 'Dom'
        }
        self.periodo_inicio = None
        self.periodo_fim = None

    def update_progress(self, current_step, total_steps, message, status='processing'):
        """Atualiza o progresso da tarefa usando o objeto job do RQ."""
        if self.job:
            effective_total_steps = total_steps if total_steps > 0 else 1
            progress_percent = int((current_step / effective_total_steps) * 100)
            self.job.meta.update({
                'progress': progress_percent,
                'message': message,
                'current_step': current_step,
                'total_steps': total_steps,
                'status': status,
                'timestamp': datetime.now().isoformat()
            })
            self.job.save()
            print(f"[RQ Job {self.job.id}] Progress: {progress_percent}% - {message}")

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
            print(f"Erro ao converter PDF para imagens: {str(e)}")
            if self.job:
                self.job.meta['error'] = f"Erro ao converter PDF: {str(e)}"
                self.job.meta['message'] = f"Erro ao converter PDF: {str(e)}"
                self.job.meta['status'] = 'error'
                self.job.save()
            return []

    def extrair_texto_completo(self, imagem):
        """Extrai todo o texto da página usando OCR"""
        try:
            img_cv = cv2.cvtColor(np.array(imagem), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            gray = cv2.bilateralFilter(gray, 9, 75, 75)
            texto = pytesseract.image_to_string(gray, config=self.config_ocr)
            return texto
        except Exception as e:
            print(f"Erro ao extrair texto com OCR: {e}")
            return ""

    def extrair_periodo_documento(self, texto):
        """Extrai o período do documento (ex: 16.01.2019 a 15.02.2019)"""
        match = re.search(r'Período:\s*(\d{1,2}\.\d{1,2}\.\d{4})\s*a\s*(\d{1,2}\.\d{1,2}\.\d{4})', texto)
        if not match:
            match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}\.\d{1,2}\.\d{4})', texto)
        if match:
            try:
                self.periodo_inicio = datetime.strptime(match.group(1), '%d.%m.%Y')
                self.periodo_fim = datetime.strptime(match.group(2), '%d.%m.%Y')
                return True
            except ValueError:
                return False
        return False

    def detectar_inicio_tabela(self, linhas):
        """Detecta onde a tabela de ponto começa."""
        header_keywords_sets = [
            [r'\bDia\b', r'\bJornada\b'],
            [r'\bDia\b', r'\bApontamento\b'],
            [r'\bDia\b', r'\bENT\.1\b', r'\bSAI\.1\b'],
            [r'\bOcor\b', r'\bRedutor\b', r'\bJornada\b', r'\bApontamento\b', r'\bNoturno\b']
        ]
        for i, linha in enumerate(linhas):
            linha_upper = linha.upper()
            for keywords_set in header_keywords_sets:
                if all(re.search(kw, linha_upper) for kw in keywords_set):
                    return i
        palavras_especiais_regex = r'|'.join([re.escape(p) for p in ['FOLG', 'COMP', 'FER', 'ATESTADO', 'REPOSO', 'FOLGA', 'DESCANSO', 'FERIADO', 'ABONO', 'FÉRIAS', '0100']])
        for i, linha in enumerate(linhas):
            is_date_pattern = re.search(r'^\s*(\d{1,2})\s+[A-Z]', linha)
            has_time_or_special_word = re.search(r'\b([0-2]?\d:[0-5]\d)\b', linha) or \
                                         re.search(palavras_especiais_regex, linha, re.IGNORECASE)
            if is_date_pattern and has_time_or_special_word:
                return i
        return 0

    def detectar_fim_tabela(self, linhas, indice_inicio):
        """Detecta onde a tabela de ponto termina."""
        palavras_fim = [
            'Hrs Normais', 'Ad. Not.', 'Total for the Month',
            'Assinatura do Funcionário', 'assinatura', 'funcionário',
            'chefia', 'visto', 'total', 'observações', 'resumo',
            'Período Banco Horas:', 'BH do Mês:'
        ]
        for i in range(indice_inicio, len(linhas)):
            linha = linhas[i].strip()
            if not linha:
                continue
            if any(re.search(r'\b' + re.escape(p) + r'\b', linha, re.IGNORECASE) for p in palavras_fim):
                return i
        return len(linhas)

    def validar_horarios(self, horarios_validos_brutos):
        """Valida os horários seguindo as regras."""
        horarios_validos = list(horarios_validos_brutos)
        while len(horarios_validos) < 4:
            horarios_validos.append("0")
        horarios_validos = horarios_validos[:4]
        entrada1, saida1, entrada2, saida2 = horarios_validos
        horarios_nao_zero = [h for h in horarios_validos if h != "0"]
        if len(horarios_nao_zero) == 1:
            return ["0", "0", "0", "0"]
        if entrada1 != "0" and saida1 == "0":
            entrada1 = "0"
            saida1 = "0"
        elif entrada1 == "0" and saida1 != "0":
            saida1 = "0"
        if entrada2 != "0" and saida2 == "0":
            entrada2 = "0"
            saida2 = "0"
        elif entrada2 == "0" and saida2 != "0":
            saida2 = "0"
        return [entrada1, saida1, entrada2, saida2]

    def processar_texto_ponto(self, texto):
        """Processa o texto extraído para encontrar dados de ponto."""
        if not self.extrair_periodo_documento(texto):
            return []
        linhas = texto.split('\n')
        indice_inicio = self.detectar_inicio_tabela(linhas)
        indice_fim = self.detectar_fim_tabela(linhas, indice_inicio)
        if indice_inicio >= indice_fim:
            return []
        linhas_tabela = linhas[indice_inicio:indice_fim]
        palavras_especiais = [
            'FOLG', 'COMP', 'FER', 'ATESTADO', 'REPOSO', 'FOLGA', 'DESCANSO', 'FERIADO', 'ABONO', 'FÉRIAS', '0100'
        ]
        dados_extraidos = []
        current_date_tracker = self.periodo_inicio
        while current_date_tracker <= self.periodo_fim:
            data_str = current_date_tracker.strftime('%d/%m/%Y')
            found_entry = False
            for linha in linhas_tabela:
                linha = linha.strip()
                if not linha:
                    continue
                day_match = re.search(r'^\s*(\d{1,2})\s+[A-Z]', linha)
                if day_match:
                    day_num = int(day_match.group(1))
                    if day_num == current_date_tracker.day:
                        parte_para_horarios = linha[day_match.end():]
                        horarios = re.findall(r'\b([0-2]?\d:[0-5]\d)\b', parte_para_horarios)
                        horarios_processados = self.validar_horarios(horarios)
                        dados_linha = {
                            'Dia': data_str,
                            'Dia_Semana': self.dias_semana_map.get(current_date_tracker.strftime('%a'), ''),
                            'Entrada1': horarios_processados[0],
                            'Saida1': horarios_processados[1],
                            'Entrada2': horarios_processados[2],
                            'Saida2': horarios_processados[3]
                        }
                        dados_extraidos.append(dados_linha)
                        found_entry = True
                        break
            if not found_entry:
                dados_linha = {
                    'Dia': data_str,
                    'Dia_Semana': self.dias_semana_map.get(current_date_tracker.strftime('%a'), ''),
                    'Entrada1': '0',
                    'Saida1': '0',
                    'Entrada2': '0',
                    'Saida2': '0'
                }
                dados_extraidos.append(dados_linha)
            current_date_tracker += timedelta(days=1)
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
            if self.job and self.job.meta.get('status') != 'error':
                   self.update_progress(1, 1, "Erro: Não foi possível converter o PDF ou nenhuma página encontrada.", status='error')
            return []
        total_paginas_reais = len(imagens)
        if self.job:
            self.job.meta['total_steps'] = total_paginas_reais
            self.job.save()
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
# CORREÇÃO: Adicionado 'user_id' na assinatura da função
def process_pdf_task(pdf_path, pages, model_type, user_id):
    """Função principal para ser executada pelo RQ Worker."""
    job = get_current_job()
    if not job:
        print("Erro: Não foi possível obter o objeto job do RQ.")
        return None

    # CORREÇÃO: Armazena o user_id no meta do job
    job.meta['user_id'] = user_id
    job.save_meta() # Salva as alterações no meta

    try:
        extrator = ExtractorPontoEletronico(model_type, job=job, debug_mode=False)
        tabelas = extrator.processar_pdf_completo(pdf_path, pages)
        if not tabelas:
            if job.meta.get('status') != 'error':
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
        df_final.to_csv(output, index=False, sep=';', encoding='utf-8')
        output.seek(0)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'BRF_ponto_extraido_{timestamp}.csv'
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
        return temp_file_path
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
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)
            print(f"PDF temporário {pdf_path} removido pelo worker.")

