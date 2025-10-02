# /opt/pontua/AutoPonto/backend_api/extractor_minuano.py
import os
import re
import tempfile
from datetime import datetime, timedelta
from io import BytesIO
import cv2
import numpy as np
import pandas as pd
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
from rq import get_current_job
# Caminho do Tesseract para Linux
import platform
if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

class ExtractorPontoEletronico:
    def __init__(self, model_type='4', job=None): # model_type='4' para Minuano
        self.model_type = model_type
        self.config_ocr = r'--oem 3 --psm 6 -l por'
        self.job = job
        self.column_end_pos = -1
        self.last_inferred_date = None
        self.day_map_pt_en = {
            'seg': 'Mon', 'ter': 'Tue', 'qua': 'Wed', 'qui': 'Thu',
            'sex': 'Fri', 'sab': 'Sat', 'dom': 'Sun'
        }

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
            # ---> INÍCIO DA ALTERAÇÃO DE DESEMPENHO <---
            num_cores = os.cpu_count()
            print(f"Utilizando {num_cores} núcleos para a conversão de PDF para imagem.")

            self.update_progress(0, 1, "Convertendo PDF para imagens...")
            first_page = None
            last_page = None
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
            # ---> FIM DA ALTERAÇÃO DE DESEMPENHO <---
            self.update_progress(1, 1, f"PDF convertido com sucesso. {len(imagens)} páginas encontradas.")
            return imagens
        except Exception as e:
            self.update_progress(0, 1, f"Erro ao converter PDF para imagens: {str(e)}", status='error')
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
            text = pytesseract.image_to_string(gray, config=self.config_ocr)
            return text
        except Exception as e:
            print(f"Erro ao extrair texto com OCR: {e}")
            return ""

    def _extrair_intervalo_datas_cabecalho(self, text):
        """
        Extrai o intervalo de datas do documento (ex: "De DD/MM/YYYY a DD/MM/YYYY" ou "Ponto DD/MM/YYYY a DD/MM/YYYY")
        do texto OCR completo, geralmente do cabeçalho da página.
        Retorna (start_date, end_date) como objetos datetime. Se não encontrado,
        retorna um intervalo muito amplo (datetime.min a datetime.max) para desativar a filtragem por data.
        """
        date_pattern_flexible = r'(\d{1,2}[/.-]\d{1,2}[/.-]\d{4})'
        range_separator_flexible = r'(?:a|to|até|[-—])'
        date_range_pattern = rf'(?:De|From|Período:|Period:|Ponto)\s*[:\s]*{date_pattern_flexible}\s*{range_separator_flexible}\s*{date_pattern_flexible}'
        match = re.search(date_range_pattern, text, re.IGNORECASE)
        if match:
            start_date_str = match.group(1)
            end_date_str = match.group(2)
            try:
                for fmt in ['%d/%m/%Y', '%d.%m.%Y', '%d-%m-%Y']:
                    try:
                        start_date = datetime.strptime(start_date_str, fmt)
                        end_date = datetime.strptime(end_date_str, fmt)
                        return start_date, end_date
                    except ValueError:
                        continue
            except Exception as e:
                pass
        month_year_pattern = r'Jornada\s*-\s*(Janeiro|Fevereiro|Março|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\s*(\d{4})'
        month_names = {
            'JANEIRO': 1, 'FEVEREIRO': 2, 'MARÇO': 3, 'ABRIL': 4, 'MAIO': 5, 'JUNHO': 6,
            'JULHO': 7, 'AGOSTO': 8, 'SETEMBRO': 9, 'OUTUBRO': 10, 'NOVEMBRO': 11, 'DEZEMBRO': 12
        }
        match_my = re.search(month_year_pattern, text, re.IGNORECASE)
        if match_my:
            month_name_ocr = match_my.group(1).upper()
            year_str = match_my.group(2)
            month_num = month_names.get(month_name_ocr)
            if month_num and year_str.isdigit():
                year_num = int(year_str)
                start_date = datetime(year_num, month_num, 1)
                if month_num == 12:
                    end_date = datetime(year_num, month_num, 31)
                else:
                    end_date = datetime(year_num, month_num + 1, 1) - timedelta(days=1)
                return start_date, end_date
        fallback_start, fallback_end = datetime.min, datetime.max
        return fallback_start, fallback_end

    def _inferir_ano_data(self, day_month_str, page_start_date, page_end_date):
        """
        Tenta inferir o ano para uma data DD/MM com base no intervalo de datas do cabeçalho.
        Retorna a data formatada como 'DD/MM/YYYY' ou None se não conseguir inferir.
        """
        try:
            test_date_start_year = datetime.strptime(f"{day_month_str}/{page_start_date.year}", '%d/%m/%Y')
            if page_start_date <= test_date_start_year <= page_end_date:
                return test_date_start_year.strftime('%d/%m/%Y')
            test_date_end_year = datetime.strptime(f"{day_month_str}/{page_end_date.year}", '%d/%m/%Y')
            if page_start_date <= test_date_end_year <= page_end_date:
                return test_date_end_year.strftime('%d/%m/%Y')
            if page_start_date.year != page_end_date.year:
                test_date_next_year = datetime.strptime(f"{day_month_str}/{page_start_date.year + 1}", '%d/%m/%Y')
                if page_start_date <= test_date_next_year <= page_end_date:
                    return test_date_next_year.strftime('%d/%m/%Y')
        except ValueError:
            pass
        return None

    def _inferir_data_com_dia_semana(self, day_str, day_of_week_abbr, page_start_date, page_end_date):
        """
        Infere a data completa (DD/MM/YYYY) quando apenas o dia do mês e a abreviação do dia da semana são conhecidos,
        usando o intervalo de datas da página como contexto e a última data inferida.
        """
        original_day_str = day_str
        potential_day_vals = []
        try:
            val = int(original_day_str)
            if 1 <= val <= 31:
                potential_day_vals.append(val)
        except ValueError:
            pass
        if len(original_day_str) == 3 and original_day_str.startswith('09'):
            try:
                corrected_day_str = '0' + original_day_str[2]
                val = int(corrected_day_str)
                if 1 <= val <= 31 and val not in potential_day_vals:
                    potential_day_vals.append(val)
            except ValueError:
                pass
        if len(original_day_str) == 2 and original_day_str.startswith('9'):
            try:
                corrected_day_str = '0' + original_day_str[1]
                val = int(corrected_day_str)
                if 1 <= val <= 31 and val not in potential_day_vals:
                    potential_day_vals.append(val)
            except ValueError:
                pass
        cleaned_day_str_raw = re.sub(r'[^\d]', '', original_day_str)
        if cleaned_day_str_raw:
            if len(cleaned_day_str_raw) >= 2:
                last_two = cleaned_day_str_raw[-2:]
                try:
                    val = int(last_two)
                    if 1 <= val <= 31 and val not in potential_day_vals:
                        potential_day_vals.append(val)
                except ValueError:
                    pass
            if len(cleaned_day_str_raw) > 2:
                first_two = cleaned_day_str_raw[:2]
                try:
                    val = int(first_two)
                    if 1 <= val <= 31 and val not in potential_day_vals:
                        potential_day_vals.append(val)
                except ValueError:
                    pass
            if len(cleaned_day_str_raw) in [1, 2]:
                try:
                    val = int(cleaned_day_str_raw)
                    if 1 <= val <= 31 and val not in potential_day_vals:
                        potential_day_vals.append(val)
                except ValueError:
                    pass
        unique_potential_days = sorted(list(set(potential_day_vals)), key=lambda x: potential_day_vals.index(x) if x in potential_day_vals else len(potential_day_vals))
        inferred_date = None
        for day_val in unique_potential_days:
            current_date_iter = page_start_date
            while current_date_iter <= page_end_date:
                if current_date_iter.day == day_val and current_date_iter.strftime('%a') == self.day_map_pt_en.get(day_of_week_abbr.lower(), ''):
                    inferred_date = current_date_iter
                    break
                current_date_iter += timedelta(days=1)
            if inferred_date:
                break
        if not inferred_date and self.last_inferred_date:
            next_expected_date = self.last_inferred_date + timedelta(days=1)
            if next_expected_date.strftime('%a') == self.day_map_pt_en.get(day_of_week_abbr.lower(), '') and \
               page_start_date <= next_expected_date <= page_end_date:
                inferred_date = next_expected_date
        if inferred_date:
            self.last_inferred_date = inferred_date
            return inferred_date.strftime('%d/%m/%Y')
        else:
            return None

    def detectar_inicio_tabela(self, linhas):
        """
        Detecta onde a tabela de ponto começa, procurando por uma linha que
        contenha um dia do mês e dia da semana.
        """
        date_day_pattern = r'^\s*\d+\s+(?:Sab|Dom|Seg|Ter|Qua|Qui|Sex)'
        data_start_index = 0
        self.column_end_pos = -1
        for i, linha in enumerate(linhas):
            if re.search(date_day_pattern, linha, re.IGNORECASE):
                data_start_index = i
                return data_start_index
        return 0

    def detectar_fim_tabela(self, linhas, indice_inicio):
        """Detecta onde a tabela de ponto termina."""
        for i in range(indice_inicio, len(linhas)):
            linha = linhas[i].strip()
            if re.search(r'ESTOU DE PLENO ACORDO', linha, re.IGNORECASE) or \
               re.search(r'Assinado eletronicamente por:', linha, re.IGNORECASE) or \
               re.search(r'Total de Horas', linha, re.IGNORECASE) or \
               re.search(r'Pje', linha, re.IGNORECASE):
                return i
        return len(linhas)

    def processar_texto_ponto(self, texto_completo, page_start_date, page_end_date):
        """Processa o texto completo de uma página para extrair os dados de ponto."""
        linhas = texto_completo.split('\n')
        indice_inicio = self.detectar_inicio_tabela(linhas)
        indice_fim = self.detectar_fim_tabela(linhas, indice_inicio)
        dados_extraidos = []
        self.last_inferred_date = None # Reinicia a última data inferida para cada processamento de página
        for i in range(indice_inicio, indice_fim):
            linha = linhas[i].strip()
            if not linha:
                continue
            line_segment = linha
            data = None
            day_of_week_abbr_from_line = None
            # 1. Tenta extrair DD e dia da semana
            date_match_dd_day = re.match(r'^\s*(\d+)\s+([A-Za-z]{3})', linha, re.IGNORECASE)
            if date_match_dd_day:
                day_str = date_match_dd_day.group(1)
                day_of_week_abbr_from_line = date_match_dd_day.group(2)
                inferred_date_str = self._inferir_data_com_dia_semana(day_str, day_of_week_abbr_from_line, page_start_date, page_end_date)
                if inferred_date_str:
                    data = inferred_date_str
            else:
                # 2. Tenta extrair DD/MM
                date_match_dd_mm = re.match(r'^\s*(\d{1,2}/\d{1,2})', linha)
                if date_match_dd_mm:
                    data_str = date_match_dd_mm.group(1)
                    inferred_date_str = self._inferir_ano_data(data_str, page_start_date, page_end_date)
                    if inferred_date_str:
                        data = inferred_date_str
            # Lógica para inferir data sequencialmente se a data ainda é None
            if data is None and self.last_inferred_date:
                next_expected_date = self.last_inferred_date + timedelta(days=1)
                if page_start_date <= next_expected_date <= page_end_date:
                    line_starts_with_day_num_match = re.match(r'^\s*(\d{1,2})', linha)
                    contains_time_or_special_word = re.search(r'\b([0-2]?\d:[0-5]\d)\b', line_segment) or \
                                                     re.search(r'Folga|Ferias', line_segment, re.IGNORECASE)
                    if (line_starts_with_day_num_match and int(line_starts_with_day_num_match.group(1)) == next_expected_date.day) or \
                       (not line_starts_with_day_num_match and contains_time_or_special_word):
                        data = next_expected_date.strftime('%d/%m/%Y')
                        self.last_inferred_date = next_expected_date
            if data:
                horarios_finais = []
                codes_pattern_and_rest = re.search(r'(?:\d{3,4}\s+[A-Za-z]{2,3})\s*(.*)', line_segment)
                times_section = ""
                if codes_pattern_and_rest:
                    times_section = codes_pattern_and_rest.group(1).strip()
                else:
                    times_section = line_segment
                horarios_brutos_com_sufixo = re.findall(r'(\d{1,2}:\d{2})[A-Za-z0-9]', times_section)
                horarios_brutos = [h for h in horarios_brutos_com_sufixo]
                valid_punches = [h for h in horarios_brutos if h != '00:00']
                if re.search(r'Folga|Ferias', linha, re.IGNORECASE) and not valid_punches:
                    horarios_finais = ["0", "0", "0", "0"]
                else:
                    final_punches = ["0", "0", "0", "0"]
                    num_valid_punches = len(valid_punches)
                    if num_valid_punches >= 4:
                        final_punches[0] = valid_punches[0]
                        final_punches[1] = valid_punches[1]
                        final_punches[2] = valid_punches[-2]
                        final_punches[3] = valid_punches[-1]
                    elif num_valid_punches == 3:
                        final_punches[0] = valid_punches[0]
                        final_punches[1] = valid_punches[1]
                        final_punches[2] = valid_punches[2]
                    elif num_valid_punches == 2:
                        final_punches[0] = valid_punches[0]
                        final_punches[1] = valid_punches[1]
                    elif num_valid_punches == 1:
                        final_punches[0] = valid_punches[0]
                    horarios_finais = final_punches
                # Mapeamento do dia da semana para português
                current_date = datetime.strptime(data, '%d/%m/%Y')
                dia_semana_map = {
                    0: 'Seg', 1: 'Ter', 2: 'Qua', 3: 'Qui', 4: 'Sex', 5: 'Sab', 6: 'Dom'
                }
                dia_semana = dia_semana_map.get(current_date.weekday(), '')
                dados_linha = {
                    'Dia': data,
                    'Dia_Semana': dia_semana,
                    'Entrada1': horarios_finais[0],
                    'Saida1': horarios_finais[1],
                    'Entrada2': horarios_finais[2],
                    'Saida2': horarios_finais[3]
                }
                dados_extraidos.append(dados_linha)
            else:
                pass
        return dados_extraidos

    def processar_pagina(self, imagem, num_pagina_real, total_images_in_batch, current_image_index_in_batch):
        """Processa uma página completa usando OCR direto"""
        self.update_progress(current_image_index_in_batch, total_images_in_batch,
                             f"Processando página {num_pagina_real} de {total_images_in_batch}...")
        texto_completo = self.extrair_texto_completo(imagem)
        if not texto_completo:
            return pd.DataFrame()
        page_start_date, page_end_date = self._extrair_intervalo_datas_cabecalho(texto_completo)
        dados_extraidos = self.processar_texto_ponto(texto_completo, page_start_date, page_end_date)
        if dados_extraidos:
            df = pd.DataFrame(dados_extraidos)
            df['Pagina'] = num_pagina_real
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
        total_images_in_batch = len(imagens)
        if self.job:
            self.job.meta['total_steps'] = total_images_in_batch
            self.job.save()
        self.update_progress(0, total_images_in_batch, f"PDF convertido. {total_images_in_batch} páginas para processar.")
        todas_tabelas = []
        for i, imagem in enumerate(imagens, 1):
            if pages_range and '-' in pages_range:
                start_page_num = int(pages_range.split('-')[0])
                num_pagina_real = start_page_num + i - 1
            else:
                num_pagina_real = i
            df_pagina = self.processar_pagina(imagem, num_pagina_real, total_images_in_batch, i)
            if not df_pagina.empty:
                todas_tabelas.append(df_pagina)
        self.update_progress(total_images_in_batch, total_images_in_batch, "Consolidando dados extraídos...")
        if todas_tabelas:
            df_consolidado = pd.concat(todas_tabelas, ignore_index=True)
            df_consolidado['Dia_dt'] = pd.to_datetime(df_consolidado['Dia'], format='%d/%m/%Y', errors='coerce')
            df_consolidado.drop_duplicates(subset=['Dia_dt', 'Entrada1', 'Saida1', 'Entrada2', 'Saida2'], keep='first', inplace=True)
            df_consolidado.sort_values(by='Dia_dt', inplace=True)
            df_consolidado.drop(columns=['Dia_dt'], inplace=True)
            self.update_progress(total_images_in_batch, total_images_in_batch, "Processamento concluído com sucesso!", status='completed')
            return [df_consolidado]
        else:
            self.update_progress(total_images_in_batch, total_images_in_batch, "Nenhum dado foi extraído.", status='completed')
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
        extrator = ExtractorPontoEletronico(model_type, job=job)
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
        # Garante que as colunas finais existam e estejam na ordem correta
        colunas_finais = ['Dia', 'Dia_Semana', 'Entrada1', 'Saida1', 'Entrada2', 'Saida2']
        for col in colunas_finais:
            if col not in df_final.columns:
                df_final[col] = "0"
        df_final = df_final[colunas_finais]
        df_final = df_final.fillna("0")
        df_final = df_final.replace("", "0")
        df_final.to_csv(output, index=False, sep=';', encoding='utf-8-sig')
        output.seek(0)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'Minuano_ponto_extraido_{timestamp}.csv'
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
