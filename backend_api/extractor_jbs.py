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
from rq import get_current_job

import platform
if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

class ExtractorPontoEletronico:
    def __init__(self, model_type='1', job=None):
        self.model_type = model_type
        self.config_ocr = r'--oem 3 --psm 6 -l por'
        self.job = job

    def update_progress(self, current_step, total_steps, message, status='processing'):
        if self.job:
            effective_total_steps = total_steps if total_steps > 0 else 1
            progress_percent = int((current_step / effective_total_steps) * 100)
            self.job.meta['progress'] = progress_percent
            self.job.meta['message'] = message
            self.job.meta['current_step'] = current_step
            self.job.meta['total_steps'] = total_steps
            self.job.meta['status'] = status
            self.job.meta['timestamp'] = datetime.now().isoformat()
            self.job.save_meta()
            print(f"[RQ Job {self.job.id}] Progress: {progress_percent}% - {message}")

    def converter_pdf_imagens(self, pdf_path, pages_range=None, dpi=300):
        try:
            num_cores = os.cpu_count()
            print(f"Utilizando {num_cores} núcleos para a conversão de PDF para imagem.")

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
                    last_page=last_page,
                    thread_count=num_cores
                )
            else:
                imagens = convert_from_path(
                    pdf_path,
                    dpi=dpi,
                    thread_count=num_cores
                )
            return imagens
        except Exception as e:
            print(f"Erro ao converter PDF para imagens: {e}")
            if self.job:
                self.job.meta['error'] = f"Erro ao converter PDF: {str(e)}"
                self.job.meta['status'] = 'error'
                self.job.save_meta()
            return []

    def extrair_texto_completo(self, imagem):
        try:
            img_cv = cv2.cvtColor(np.array(imagem), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            gray = cv2.bilateralFilter(gray, 9, 75, 75)
            return pytesseract.image_to_string(gray, config=self.config_ocr)
        except Exception as e:
            print(f"Erro ao extrair texto com OCR: {e}")
            return ""

    def detectar_inicio_tabela(self, linhas):
        for i, linha in enumerate(linhas):
            if re.search(r'\b(Dia|Data)\b', linha) and re.search(r'\b(Marcação|Situação)\b', linha):
                return i
        return 0

    def detectar_fim_tabela(self, linhas, indice_inicio):
        for i in range(indice_inicio + 1, len(linhas)):
            linha = linhas[i].strip()
            if re.search(r'\b(assinatura|funcionário|chefia|visto|total|observações|Este cartão)\b', linha, re.IGNORECASE):
                return i
        return len(linhas)

    def validar_horarios(self, horarios_validos):
        while len(horarios_validos) < 4:
            horarios_validos.append("0")
        horarios_validos = horarios_validos[:4]
        horarios_nao_zero = [h for h in horarios_validos if h != "0"]
        if len(horarios_nao_zero) == 1:
            return ["0", "0", "0", "0"]
        entrada1, saida1, entrada2, saida2 = horarios_validos
        if entrada1 != "0" and saida1 == "0":
            entrada1, saida1 = "0", "0"
        if entrada1 == "0" and saida1 != "0":
            saida1 = "0"
        if entrada2 != "0" and saida2 == "0":
            entrada2, saida2 = "0", "0"
        if entrada2 == "0" and saida2 != "0":
            saida2 = "0"
        return [entrada1, saida1, entrada2, saida2]

    def processar_texto_ponto(self, texto):
        linhas = texto.split('\n')
        indice_inicio = self.detectar_inicio_tabela(linhas)
        indice_fim = self.detectar_fim_tabela(linhas, indice_inicio)
        linhas_tabela = linhas[indice_inicio:indice_fim]
        
        dados_extraidos = []

        for linha in linhas_tabela:
            linha = linha.strip()
            if not linha:
                continue

            data_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', linha)
            if data_match:
                data = data_match.group(1)
                pos_data = linha.find(data)
                inicio_busca = pos_data + len(data)
                substring_horarios = linha[inicio_busca:]
                
                # ---> INÍCIO DA ALTERAÇÃO: LÓGICA DO DIA DA SEMANA <---
                # Esta nova lógica calcula o dia da semana a partir da data,
                # ignorando o texto que pode conter erros de OCR.
                dia_semana_encontrado = ""
                try:
                    # Converte a string da data para um objeto datetime
                    data_obj = datetime.strptime(data, '%d/%m/%Y')
                    # Mapeia o dia da semana (0=Seg, 1=Ter, ..., 6=Dom) para a abreviação
                    dias_map = {0: 'Seg', 1: 'Ter', 2: 'Qua', 3: 'Qui', 4: 'Sex', 5: 'Sab', 6: 'Dom'}
                    dia_semana_encontrado = dias_map.get(data_obj.weekday(), "")
                except ValueError:
                    # Caso a data extraída seja inválida, mantém o dia da semana em branco
                    dia_semana_encontrado = ""
                # ---> FIM DA ALTERAÇÃO <---
                
                palavras_especiais = ['COMPENSA DIA', 'INTEGRAÇÃO', 'INTERAÇÃO', 'DISPENSA',
                                      'ATESTADO', 'MÉDICO', 'FALTA', 'LICENÇA', 'FÉRIAS']
                
                if any(palavra in linha.upper() for palavra in palavras_especiais):
                    horarios_validos = ["0", "0", "0", "0"]
                else:
                    todos_horarios = re.findall(r'\b([0-2]?\d:[0-5]\d)\b', substring_horarios)
                    horarios_crescentes = []
                    ultimo_horario = None

                    for horario_atual in todos_horarios:
                        if ultimo_horario is None or horario_atual > ultimo_horario:
                            horarios_crescentes.append(horario_atual)
                            ultimo_horario = horario_atual
                        else:
                            break
                    
                    horarios_validos = horarios_crescentes[:4]
                    horarios_validos = self.validar_horarios(horarios_validos)
                
                dados_linha = {
                    'Dia': data,
                    'Dia_Semana': dia_semana_encontrado,
                    'Entrada1': horarios_validos[0],
                    'Saida1': horarios_validos[1],
                    'Entrada2': horarios_validos[2],
                    'Saida2': horarios_validos[3]
                }
                dados_extraidos.append(dados_linha)
        
        return dados_extraidos

    def processar_pagina(self, imagem, num_pagina):
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
        self.update_progress(0, 1, "Iniciando processamento e convertendo PDF para imagens...")
        imagens = self.converter_pdf_imagens(pdf_path, pages_range)
        if not imagens:
            self.update_progress(1, 1, "Erro: Não foi possível converter o PDF.", status='error')
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

def process_pdf_task(pdf_path, pages, model_type, user_id):
    job = get_current_job()
    if not job:
        print("Erro: Não foi possível obter o objeto job do RQ.")
        return None
        
    job.meta['user_id'] = user_id
    job.save_meta()

    try:
        extrator = ExtractorPontoEletronico(model_type, job)
        tabelas = extrator.processar_pdf_completo(pdf_path, pages)

        if not tabelas:
            job.meta.update({
                'status': 'error',
                'error': 'Nenhuma tabela foi encontrada no PDF',
                'progress': 100,
                'message': 'Nenhuma tabela foi encontrada no PDF.'
            })
            job.save_meta()
            return None

        final_total_steps = job.meta.get('total_steps', 1)
        extrator.update_progress(final_total_steps, final_total_steps, "Gerando arquivo CSV...", status='processing')

        output = BytesIO()
        df_final = tabelas[0]
        
        df_final['Dia'] = pd.to_datetime(df_final['Dia'], format='%d/%m/%Y', errors='coerce')
        df_final.dropna(subset=['Dia'], inplace=True) 
        
        df_final = df_final.sort_values(by='Dia', ascending=True).reset_index(drop=True)
        
        df_final['Dia'] = df_final['Dia'].dt.strftime('%d/%m/%Y')

        colunas_finais = ['Dia', 'Dia_Semana', 'Entrada1', 'Saida1', 'Entrada2', 'Saida2']
        for col in colunas_finais:
            if col not in df_final.columns:
                df_final[col] = "0"
        df_final = df_final[colunas_finais]
        df_final = df_final.fillna("0").replace("", "0")
        
        df_final.to_csv(output, index=False, encoding='utf-8', sep=';')
        output.seek(0)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'JBS_ponto_extraido_{timestamp}.csv'
        
        temp_dir_for_results = os.path.join(tempfile.gettempdir(), 'pontua_results')
        os.makedirs(temp_dir_for_results, exist_ok=True)
        temp_file_path = os.path.join(temp_dir_for_results, f"{job.id}.csv")

        with open(temp_file_path, 'wb') as f:
            f.write(output.getvalue())

        job.meta.update({
            'status': 'completed',
            'file_path': temp_file_path,
            'filename': filename,
            'progress': 100,
            'message': 'Arquivo processado com sucesso!'
        })
        job.save_meta()
        return temp_file_path

    except Exception as e:
        error_message = f'Erro durante o processamento da tarefa {job.id}: {str(e)}'
        print(error_message) 
        job.meta.update({
            'status': 'error', 'error': error_message,
            'progress': 0, 'message': error_message
        })
        job.save_meta()
        return None
    finally:
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)
            print(f"PDF temporário {pdf_path} removido pelo worker.")
