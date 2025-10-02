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
from datetime import datetime, timedelta
from rq import get_current_job

import platform
if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

class ExtractorPontoEletronico:
    def __init__(self, model_type='5', job=None, jornada_contratual_config=None, hora_extra_config=None):
        self.model_type = model_type
        self.config_ocr = r'--oem 3 --psm 6 -l por'
        self.job = job
        self.jornada_contratual_config = jornada_contratual_config if jornada_contratual_config else {}
        self.hora_extra_config = hora_extra_config if hora_extra_config else {}
        self.horarios_mapeados = {} # Armazena o mapa de horários contratuais

    def update_progress(self, current_step, total_steps, message, status='processing'):
        if self.job:
            effective_total_steps = total_steps if total_steps > 0 else 1
            progress_percent = int((current_step / effective_total_steps) * 100)
            self.job.meta.update({
                'progress': progress_percent, 'message': message, 'current_step': current_step,
                'total_steps': total_steps, 'status': status, 'timestamp': datetime.now().isoformat()
            })
            self.job.save()
            print(f"[RQ Job {self.job.id}] Progress: {progress_percent}% - {message}")

    def converter_pdf_imagens(self, pdf_path, pages_range=None, dpi=300):
        try:
            # ---> INÍCIO DA ALTERAÇÃO DE DESEMPENHO <---
            num_cores = os.cpu_count()
            print(f"Utilizando {num_cores} núcleos para a conversão de PDF para imagem.")

            pages_args = {'thread_count': num_cores} # Adiciona o parâmetro para usar todos os núcleos
            if pages_range:
                if '-' in pages_range:
                    start, end = map(int, pages_range.split('-'))
                    pages_args['first_page'] = start
                    pages_args['last_page'] = end
                else:
                    pages_args['first_page'] = pages_args['last_page'] = int(pages_range)
            
            return convert_from_path(pdf_path, dpi=dpi, **pages_args)
            # ---> FIM DA ALTERAÇÃO DE DESEMPENHO <---
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

    def _extrair_horarios_contratuais(self, texto):
        self.horarios_mapeados = {}
        linhas = texto.split('\n')
        tabela_encontrada = False
        for linha in linhas:
            if 'Horários contratuais do empregado' in linha:
                tabela_encontrada = True
                continue
            if not tabela_encontrada:
                continue
            if 'Motivos de tratamento' in linha:
                break
            
            match = re.match(r'^\s*(\d{4})\s+(\d{1,2}:\d{2})\s+(\d{1,2}:\d{2})(?:\s+(\d{1,2}:\d{2}))?(?:\s+(\d{1,2}:\d{2}))?', linha)
            if match:
                codigo = match.group(1)
                horarios = [h for h in match.groups()[1:] if h]
                while len(horarios) < 4:
                    horarios.append("0")
                self.horarios_mapeados[codigo] = horarios

    def validar_horarios(self, horarios):
        """
        Valida os horários. Se houver apenas um horário, zera todos.
        Garante que a lista tenha sempre 4 elementos.
        """
        horarios_validos = list(horarios)[:4]
        
        horarios_nao_zero = [h for h in horarios_validos if h and h != "0"]

        if len(horarios_nao_zero) == 1:
            return ["0", "0", "0", "0"]

        while len(horarios_validos) < 4:
            horarios_validos.append("0")
            
        return [h if h else "0" for h in horarios_validos]

    def processar_texto_ponto(self, texto):
        self._extrair_horarios_contratuais(texto)
        linhas = texto.split('\n')
        dados_extraidos = []
        
        for linha in linhas:
            linha = linha.strip()
            if not linha:
                continue
            
            match = re.match(r'^\s*(\d{2}/\d{2}/\d{2})\s*[\]|/]*\s*([A-ZÁ]{3})\.?[|]?\s*(.*)', linha)
            if match:
                data_str, dia_semana, resto_linha = match.groups()
                dia_semana = dia_semana.upper().replace('Á', 'A').replace('.', '')
                
                try:
                    data_obj = datetime.strptime(data_str, '%d/%m/%y')
                    data = data_obj.strftime('%d/%m/%Y')
                except ValueError:
                    continue

                horarios_provisorios = ["0", "0", "0", "0"]
                is_jornada_contratual = "Trabalho conforme jornada contratual" in resto_linha

                if is_jornada_contratual and self.jornada_contratual_config.get('tipo') == 'codigo_horario':
                    codigo_horario_match = re.search(r'\s(\d{4})\s', linha)
                    if codigo_horario_match:
                        codigo = codigo_horario_match.group(1)
                        if codigo in self.horarios_mapeados:
                            horarios_provisorios = self.horarios_mapeados[codigo][:]

                jornada_realizada_texto = resto_linha
                fim_busca_match = re.search(r'Horas extras|Ad\. Not\.|Faltas/|Trat\. Aus\.|BH saldo|%', resto_linha, re.IGNORECASE)
                if fim_busca_match:
                    jornada_realizada_texto = resto_linha[:fim_busca_match.start()]
                
                horarios_batidos = re.findall(r'(\d{1,2}:\d{2})\(\d\)', jornada_realizada_texto)
                if horarios_batidos:
                    for i in range(min(len(horarios_batidos), 4)):
                        horarios_provisorios[i] = horarios_batidos[i]

                if self.jornada_contratual_config.get('tipo') == 'codigo_horario' and self.hora_extra_config.get('adicionar_1h'):
                    if is_jornada_contratual and any(he in resto_linha for he in ['150%', '100%', '50%']):
                        indice_ultima_saida = -1
                        if horarios_provisorios[3] not in ["0", None]:
                            indice_ultima_saida = 3
                        elif horarios_provisorios[1] not in ["0", None]:
                            indice_ultima_saida = 1

                        if indice_ultima_saida != -1:
                            try:
                                saida_dt = datetime.strptime(horarios_provisorios[indice_ultima_saida], '%H:%M')
                                saida_dt += timedelta(hours=1)
                                horarios_provisorios[indice_ultima_saida] = saida_dt.strftime('%H:%M')
                            except ValueError:
                                pass
                
                # Validação universal aplicada aqui
                horarios_finais = self.validar_horarios(horarios_provisorios)

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
        if not texto_completo: return pd.DataFrame()
        dados_extraidos = self.processar_texto_ponto(texto_completo)
        if dados_extraidos:
            df = pd.DataFrame(dados_extraidos)
            df['Pagina'] = num_pagina
            return df
        return pd.DataFrame()

    def fill_missing_dates(self, df):
        if df.empty:
            return df
        try:
            df['Dia_dt'] = pd.to_datetime(df['Dia'], format='%d/%m/%Y')
            df = df.drop_duplicates(subset=['Dia_dt']).set_index('Dia_dt')

            data_inicio = df.index.min()
            data_fim = df.index.max()
            intervalo_completo = pd.date_range(start=data_inicio, end=data_fim)
            
            df_completo = df.reindex(intervalo_completo)
            df_completo['Dia'] = df_completo.index.strftime('%d/%m/%Y')

            dia_semana_map = {0: 'SEG', 1: 'TER', 2: 'QUA', 3: 'QUI', 4: 'SEX', 5: 'SAB', 6: 'DOM'}
            df_completo['Dia_Semana'] = df_completo.index.dayofweek.map(dia_semana_map)
            
            return df_completo.reset_index(drop=True)
        except Exception as e:
            print(f"Aviso: Falha ao preencher dias faltantes. Erro: {e}")
            if 'Dia_dt' in df.columns:
                return df.drop(columns=['Dia_dt'])
            return df

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
            df_final = self.fill_missing_dates(df_consolidado)
            self.update_progress(total_paginas, total_paginas, "Processamento concluído!", status='completed')
            return [df_final]
        
        self.update_progress(total_paginas, total_paginas, "Nenhum dado extraído.", status='completed')
        return []

def process_pdf_task(pdf_path, pages, model_type, user_id, jornada_contratual_config=None, hora_extra_config=None):
    job = get_current_job()
    if not job:
        print("Erro: Não foi possível obter o objeto job do RQ.")
        return None

    job.meta['user_id'] = user_id
    job.save_meta()

    try:
        extrator = ExtractorPontoEletronico(model_type, job, jornada_contratual_config, hora_extra_config)
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
        df_final = df_final[colunas_finais].fillna("0").replace("", "0")

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
