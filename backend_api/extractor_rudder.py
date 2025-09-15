# /opt/pontua/AutoPonto/backend_api/extractor_rudder.py
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
from rq import get_current_job

import platform
if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

class ExtractorPontoEletronico:
    def __init__(self, model_type='5', job=None): # Model type '5' para Rudder
        self.model_type = model_type
        self.config_ocr = r'--oem 3 --psm 6 -l por'
        self.job = job

    def update_progress(self, current_step, total_steps, message, status='processing'):
        if self.job:
            effective_total_steps = total_steps if total_steps > 0 else 1
            progress_percent = int((current_step / effective_total_steps) * 100)
            self.job.meta.update({
                'progress': progress_percent, 'message': message, 'current_step': current_step,
                'total_steps': total_steps, 'status': status, 'timestamp': datetime.now().isoformat()
            })
            self.job.save()
            # O print no worker pode ser útil para monitorização
            print(f"[RQ Job {self.job.id}] Progress: {progress_percent}% - {message}")

    def converter_pdf_imagens(self, pdf_path, pages_range=None, dpi=300):
        try:
            pages_args = {}
            if pages_range:
                if '-' in pages_range:
                    start, end = map(int, pages_range.split('-'))
                    pages_args['first_page'] = start
                    pages_args['last_page'] = end
                else:
                    pages_args['first_page'] = pages_args['last_page'] = int(pages_range)
            return convert_from_path(pdf_path, dpi=dpi, **pages_args)
        except Exception as e:
            print(f"Erro ao converter PDF para imagens: {e}")
            if self.job:
                self.job.meta['error'] = f"Erro ao converter PDF: {str(e)}"
                self.job.meta['status'] = 'error'
                self.job.save()
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
            if re.match(r'^\s*(\d{2}/\d{2}/\d{2}).*?\s+([A-ZÁ]{3})\.?', linha):
                return i
        return 0

    def detectar_fim_tabela(self, linhas, indice_inicio):
        for i in range(indice_inicio, len(linhas)):
            if linhas[i].strip().startswith('Total:'):
                return i
        return len(linhas)

    def processar_texto_ponto(self, texto):
        linhas = texto.split('\n')
        indice_inicio = self.detectar_inicio_tabela(linhas)
        indice_fim = self.detectar_fim_tabela(linhas, indice_inicio)
        
        if indice_inicio == 0 and not any(re.match(r'^\s*(\d{2}/\d{2}/\d{2})', l) for l in linhas):
             return []

        linhas_tabela = linhas[indice_inicio:indice_fim]
        dados_extraidos = []
        
        for linha in linhas_tabela:
            linha = linha.strip()
            if not linha:
                continue
            
            match = re.match(r'^\s*(\d{2}/\d{2}/\d{2})\s*[\]|/]*\s*([A-ZÁ]{3})\.?[|]?\s*(.*)', linha)
            if match:
                data_str, dia_semana, resto_linha = match.groups()
                dia_semana = dia_semana.upper().replace('Á', 'A')
                
                try:
                    data_obj = datetime.strptime(data_str, '%d/%m/%y')
                    data = data_obj.strftime('%d/%m/%Y')
                except ValueError:
                    continue

                horarios_finais = ["0", "0", "0", "0"]
                
                horarios = re.findall(r'(\d{2}:\d{2})\(\d\)', resto_linha)

                if len(horarios) > 0:
                    if len(horarios) >= 2:
                        horarios_finais[0] = horarios[0]
                        horarios_finais[1] = horarios[1]
                    elif len(horarios) == 1:
                        horarios_finais[0] = horarios[0]
                else:
                    palavras_especiais = ['FOLGA', 'TRABALHO CONFORME JORNADA CONTRATUAL']
                    if not any(palavra in resto_linha.upper() for palavra in palavras_especiais):
                        # Se não encontrou horários nem palavras especiais, pode ser um erro de OCR,
                        # mas por segurança, assume-se como dia não trabalhado.
                        pass

                dados_linha = {
                    'Dia': data,
                    'Dia_Semana': dia_semana,
                    'Entrada1': horarios_finais[0],
                    'Saida1': horarios_finais[1],
                    'Entrada2': horarios_finais[2],
                    'Saida2': horarios_finais[3]
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
        return pd.DataFrame()

    def processar_pdf_completo(self, pdf_path, pages_range=None):
        self.update_progress(0, 1, "A iniciar processamento...")
        imagens = self.converter_pdf_imagens(pdf_path, pages_range)
        if not imagens:
            self.update_progress(1, 1, "Erro: Não foi possível converter o PDF.", status='error')
            return []
        
        total_paginas = len(imagens)
        self.update_progress(0, total_paginas, f"PDF convertido. {total_paginas} páginas para processar.")
        
        todas_tabelas = []
        for i, imagem in enumerate(imagens, 1):
            num_pagina_real = i
            if pages_range and '-' in pages_range:
                start_page = int(pages_range.split('-')[0])
                num_pagina_real = start_page + i - 1

            self.update_progress(i, total_paginas, f"A processar página {num_pagina_real}...")
            df_pagina = self.processar_pagina(imagem, num_pagina_real)
            if not df_pagina.empty:
                todas_tabelas.append(df_pagina)
        
        if todas_tabelas:
            df_consolidado = pd.concat(todas_tabelas, ignore_index=True)
            self.update_progress(total_paginas, total_paginas, "Processamento concluído!", status='completed')
            return [df_consolidado]
        
        self.update_progress(total_paginas, total_paginas, "Nenhum dado extraído.", status='completed')
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
            job.meta.update({'status': 'error', 'error': 'Nenhuma tabela encontrada no PDF.'})
            job.save()
            return None

        df_final = tabelas[0]
        colunas_finais = ['Dia', 'Dia_Semana', 'Entrada1', 'Saida1', 'Entrada2', 'Saida2']
        for col in colunas_finais:
            if col not in df_final.columns:
                df_final[col] = "0"
        df_final = df_final[colunas_finais].fillna("0")

        output = BytesIO()
        df_final.to_csv(output, index=False, encoding='utf-8', sep=';')
        output.seek(0)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'Rudder_ponto_extraido_{timestamp}.csv'
        
        temp_file_path = os.path.join(tempfile.gettempdir(), f"{job.id}.csv")
        with open(temp_file_path, 'wb') as f:
            f.write(output.getvalue())

        job.meta.update({
            'status': 'completed', 'file_path': temp_file_path,
            'filename': filename, 'progress': 100,
            'message': 'Ficheiro processado com sucesso!'
        })
        job.save()
        return temp_file_path
    except Exception as e:
        error_message = f'Erro na tarefa {job.id}: {str(e)}'
        print(error_message)
        job.meta.update({'status': 'error', 'error': error_message})
        job.save()
        return None
    finally:
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)
