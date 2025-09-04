import os
import re
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta
from io import BytesIO
import cv2
import numpy as np
import pandas as pd
import pytesseract
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from pdf2image import convert_from_path
from PIL import Image
import platform
# Configuração do logger removida para produção
app = Flask(__name__)
CORS(app)
if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
# Armazenamento em memória para o progresso das tarefas
task_progress = {}
class ExtractorPontoEletronico:
    def __init__(self, model_type='1', task_id=None):
        self.model_type = model_type
        self.config_ocr = r'--oem 3 --psm 6 -l por'
        self.task_id = task_id
        self.column_end_pos = -1
        self.last_inferred_date = None
        self.day_map_pt_en = {
            'seg': 'Mon', 'ter': 'Tue', 'qua': 'Wed', 'qui': 'Thu',
            'sex': 'Fri', 'sab': 'Sat', 'dom': 'Sun'
        }
    def update_progress(self, current_step, total_steps, message):
        """Atualiza o progresso da tarefa"""
        if self.task_id:
            # Garante que total_steps não seja zero para evitar divisão por zero
            effective_total_steps = total_steps if total_steps > 0 else 1
            progress_percent = int((current_step / effective_total_steps) * 100)
            task_progress[self.task_id].update({
                'progress': progress_percent,
                'message': message,
                'current_step': current_step, # current_step agora será o índice da página no lote
                'total_steps': total_steps, # total_steps agora será o total de páginas no lote
                'timestamp': datetime.now().isoformat()
            })
    def converter_pdf_imagens(self, pdf_path, pages_range=None, dpi=300):
        """Converte PDF para imagens"""
        try:
            # Progresso para a fase de conversão: 0 de 1 (antes de iniciar), 1 de 1 (após concluir)
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
                    last_page=last_page
                )
            else:
                imagens = convert_from_path(pdf_path, dpi=dpi)
            # Concluída a conversão (1 de 1 passo para esta fase)
            self.update_progress(1, 1, f"PDF convertido com sucesso. {len(imagens)} páginas encontradas.")
            return imagens
        except Exception as e:
            # Erro na conversão (0 de 1 passo para esta fase)
            self.update_progress(0, 1, f"Erro ao converter PDF para imagens: {str(e)}")
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
            day_of_week_abbr_from_line = None # Para armazenar a abreviação se encontrada

            # 1. Tenta extrair DD e dia da semana
            date_match_dd_day = re.match(r'^\s*(\d+)\s+([A-Za-z]{3})', linha, re.IGNORECASE)
            if date_match_dd_day:
                day_str = date_match_dd_day.group(1)
                day_of_week_abbr_from_line = date_match_dd_day.group(2)
                # Tenta inferir a data com base no que foi lido
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

            # NOVO: Lógica para inferir data sequencialmente se a data ainda é None
            # Isso cobre casos onde o dia ou a abreviação da semana não foram lidos corretamente.
            if data is None and self.last_inferred_date:
                next_expected_date = self.last_inferred_date + timedelta(days=1)

                # Verifica se a próxima data esperada está dentro do intervalo de datas do cabeçalho da página
                if page_start_date <= next_expected_date <= page_end_date:
                    # Heurística para decidir se esta linha deve receber a data inferida:
                    # 1. A linha começa com um número de dia que corresponde ao dia esperado?
                    # 2. OU, a linha contém algum padrão de horário (mesmo que "00:00") ou uma palavra especial (Folga/Ferias)?

                    line_starts_with_day_num_match = re.match(r'^\s*(\d{1,2})', linha)
                    contains_time_or_special_word = re.search(r'\b([0-2]?\d:[0-5]\d)\b', line_segment) or \
                                                    re.search(r'Folga|Ferias', line_segment, re.IGNORECASE)

                    # Se a linha começa com um número de dia e ele corresponde ao dia esperado,
                    # OU se a linha não começa com um número de dia, mas contém horários/palavras especiais (indicando que é uma linha de dados)
                    if (line_starts_with_day_num_match and int(line_starts_with_day_num_match.group(1)) == next_expected_date.day) or \
                       (not line_starts_with_day_num_match and contains_time_or_special_word):
                        data = next_expected_date.strftime('%d/%m/%Y')
                        self.last_inferred_date = next_expected_date

            if data: # Só processa a linha se a data foi inferida com sucesso
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
                dados_linha = {
                    'Data': data,
                    '1ª Entrada': horarios_finais[0],
                    '1ª Saída': horarios_finais[1],
                    '2ª Entrada': horarios_finais[2],
                    '2ª Saída': horarios_finais[3]
                }
                dados_extraidos.append(dados_linha)
            else:
                pass # Linha ignorada se a data não pôde ser inferida
        return dados_extraidos
    def processar_pagina(self, imagem, num_pagina_real, total_images_in_batch, current_image_index_in_batch): # Adicionado current_image_index_in_batch
        """Processa uma página completa usando OCR direto"""
        # current_step será o índice da imagem no lote (1 a total_images_in_batch)
        # total_steps será o total de imagens no lote
        # A mensagem incluirá o número da página real do PDF
        self.update_progress(current_image_index_in_batch, total_images_in_batch,
                             f"Processando página {num_pagina_real} de {total_images_in_batch}...")
        texto_completo = self.extrair_texto_completo(imagem)
        if not texto_completo:
            return pd.DataFrame()
        page_start_date, page_end_date = self._extrair_intervalo_datas_cabecalho(texto_completo)
        dados_extraidos = self.processar_texto_ponto(texto_completo, page_start_date, page_end_date)
        if dados_extraidos:
            df = pd.DataFrame(dados_extraidos)
            df['Pagina'] = num_pagina_real # Armazena o número da página real do PDF
            return df
        else:
            return pd.DataFrame()
    def processar_pdf_completo(self, pdf_path, pages_range=None):
        """Processa PDF completo"""
        # Inicializa o progresso: 0 de 1 (fase de conversão)
        self.update_progress(0, 1, "Iniciando processamento e convertendo PDF para imagens...")
        imagens = self.converter_pdf_imagens(pdf_path, pages_range)
        if not imagens:
            # Se não houver imagens, o progresso final é 0/1, status de erro
            self.update_progress(0, 1, "Erro: Não foi possível converter o PDF ou nenhuma página encontrada.")
            return []
        total_images_in_batch = len(imagens) # Este é o número de imagens no intervalo selecionado
        # ATUALIZAÇÃO CRÍTICA: Define o total_steps real no task_progress para o total de páginas do lote
        if self.task_id:
            task_progress[self.task_id]['total_steps'] = total_images_in_batch
        # Atualiza o progresso para indicar que a conversão foi concluída e quantas páginas serão processadas
        # current_step 0, total_steps = total_images_in_batch para iniciar o loop de páginas
        self.update_progress(0, total_images_in_batch, f"PDF convertido. {total_images_in_batch} páginas para processar.")
        todas_tabelas = []
        for i, imagem in enumerate(imagens, 1): # 'i' será 1, 2, ..., total_images_in_batch (índice no lote)
            if pages_range and '-' in pages_range:
                start_page_num = int(pages_range.split('-')[0])
                num_pagina_real = start_page_num + i - 1 # Este é o número da página real do PDF
            else:
                num_pagina_real = i # Se não houver intervalo, é apenas 1, 2, 3...
            # Chama processar_pagina com os parâmetros corretos para o progresso
            # num_pagina_real para a mensagem, i para o current_step do progresso
            df_pagina = self.processar_pagina(imagem, num_pagina_real, total_images_in_batch, i)
            if not df_pagina.empty:
                todas_tabelas.append(df_pagina)
        # Após o loop, atualiza o progresso para a consolidação dos dados
        # current_step = total_images_in_batch para indicar 100% de páginas processadas
        self.update_progress(total_images_in_batch, total_images_in_batch, "Consolidando dados extraídos...")
        if todas_tabelas:
            df_consolidado = pd.concat(todas_tabelas, ignore_index=True)
            df_consolidado['Data_dt'] = pd.to_datetime(df_consolidado['Data'], format='%d/%m/%Y', errors='coerce')
            df_consolidado.drop_duplicates(subset=['Data_dt', '1ª Entrada', '1ª Saída', '2ª Entrada', '2ª Saída'], keep='first', inplace=True)
            df_consolidado.sort_values(by='Data_dt', inplace=True)
            df_consolidado.drop(columns=['Data_dt'], inplace=True)
            # Finaliza o progresso com 100%
            self.update_progress(total_images_in_batch, total_images_in_batch, "Processamento concluído com sucesso!")
            return [df_consolidado]
        else:
            # Se nenhum dado foi extraído, atualiza o progresso para indicar isso
            self.update_progress(total_images_in_batch, total_images_in_batch, "Nenhum dado foi extraído.")
            return []
# Função para processar em background
def process_pdf_background(task_id, pdf_path, pages, model_type):
    """Processa o PDF em background e gera um arquivo CSV"""
    try:
        extrator = ExtractorPontoEletronico(model_type, task_id)
        tabelas = extrator.processar_pdf_completo(pdf_path, pages)
        if not tabelas:
            task_progress[task_id]['status'] = 'error'
            task_progress[task_id]['error'] = 'Nenhuma tabela foi encontrada no PDF'
            # Garante que total_steps seja pelo menos 1 se ainda for 0 de um erro inicial
            if task_progress[task_id].get('total_steps', 0) == 0:
                task_progress[task_id]['total_steps'] = 1
            return
        # Pega o total de páginas do último update de progresso bem-sucedido
        final_total_pages = task_progress[task_id].get('total_steps', 0)
        extrator.update_progress(final_total_pages, final_total_pages, "Gerando arquivo CSV...")
        output = BytesIO()
        df_final = tabelas[0]
        df_final['Data'] = pd.to_datetime(df_final['Data'], format='%d/%m/%Y', errors='coerce')
        weekday_map = {
            'Mon': 'Seg', 'Tue': 'Ter', 'Wed': 'Qua', 'Thu': 'Qui',
            'Fri': 'Sex', 'Sat': 'Sab', # ALTERAÇÃO AQUI: 'Sat' para 'Sab'
            'Sun': 'Dom'
        }
        df_final['Dia_Semana'] = df_final['Data'].dt.strftime('%a').map(weekday_map)
        df_final['Data'] = df_final['Data'].dt.strftime('%d/%m/%Y')
        colunas_finais = ['Data', 'Dia_Semana', '1ª Entrada', '1ª Saída', '2ª Entrada', '2ª Saída']
        for col in colunas_finais:
            if col not in df_final.columns:
                df_final[col] = "0"
        df_final = df_final[colunas_finais]
        df_final = df_final.fillna("0")
        df_final = df_final.replace("", "0")
        df_final.to_csv(output, index=False, sep=';', encoding='utf-8-sig')
        output.seek(0)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'Ponto_pontomais_extraido_{timestamp}.csv'
        temp_file_path = os.path.join(tempfile.gettempdir(), f"{task_id}.csv")
        with open(temp_file_path, 'wb') as f:
            f.write(output.getvalue())
        time.sleep(0.5)
        # Garante que current_step e total_steps estejam presentes no estado de conclusão
        task_progress[task_id].update({
            'status': 'completed',
            'file_path': temp_file_path,
            'filename': filename,
            'progress': 100,
            'message': 'Arquivo processado com sucesso!',
            'current_step': final_total_pages, # Define a página atual como o total na conclusão
            'total_steps': final_total_pages
        })
    except Exception as e:
        # Garante que current_step e total_steps estejam presentes no estado de erro
        # E que total_steps seja pelo menos 1, se não tiver sido definido ainda
        if task_id in task_progress and task_progress[task_id].get('total_steps', 0) == 0:
            task_progress[task_id]['total_steps'] = 1
        task_progress[task_id].update({
            'status': 'error',
            'error': str(e),
            'progress': 0,
            'message': f'Erro durante o processamento: {str(e)}',
            'current_step': task_progress[task_id].get('current_step', 0), # Mantém a última página relatada ou 0
            'total_steps': task_progress[task_id].get('total_steps', 1) # Mantém o total relatado ou 1
        })
    finally:
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)
@app.route('/process', methods=['POST'])
def process_pdf():
    try:
        if 'pdf_file' not in request.files:
            return jsonify({'error': 'Nenhum arquivo PDF foi enviado'}), 400
        file = request.files['pdf_file']
        pages = request.form.get('pages', '')
        model_type = request.form.get('model_type', '1')
        if file.filename == '':
            return jsonify({'error': 'Nenhum arquivo selecionado'}), 400
        task_id = str(uuid.uuid4())
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            file.save(tmp_file.name)
            pdf_path = tmp_file.name
        # Inicializa task_progress com total_steps como 1 (placeholder para a fase de conversão)
        task_progress[task_id] = {
            'progress': 0,
            'message': 'Tarefa iniciada...',
            'status': 'processing',
            'current_step': 0,
            'total_steps': 1, # Placeholder, será atualizado pelo ExtractorPontoEletronico com o número de páginas reais
            'timestamp': datetime.now().isoformat()
        }
        thread = threading.Thread(
            target=process_pdf_background,
            args=(task_id, pdf_path, pages, model_type)
        )
        thread.daemon = True
        thread.start()
        return jsonify({
            'task_id': task_id,
            'message': 'Processamento iniciado',
            'status': 'processing'
        })
    except Exception as e:
        # Em caso de erro inicial, garante que total_steps seja pelo menos 1
        if task_id in task_progress and task_progress[task_id].get('total_steps', 0) == 0:
            task_progress[task_id]['total_steps'] = 1
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500
@app.route('/progress/<task_id>', methods=['GET'])
def get_progress(task_id):
    if task_id not in task_progress:
        return jsonify({'error': 'Tarefa não encontrada'}), 404
    return jsonify(task_progress[task_id])
@app.route('/download/<task_id>', methods=['GET'])
def download_result(task_id):
    if task_id not in task_progress:
        return jsonify({'error': 'Tarefa não encontrada'}), 404
    task_info = task_progress[task_id]
    if task_info.get('status') != 'completed':
        return jsonify({'error': 'Tarefa ainda não foi concluída'}), 400
    file_path = task_info.get('file_path')
    filename = task_info.get('filename')
    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'Arquivo não encontrado'}), 404
    def remove_file():
        """Remove o arquivo após o download"""
        time.sleep(5)
        try:
            os.unlink(file_path)
            del task_progress[task_id]
        except Exception as e:
            pass
    cleanup_thread = threading.Thread(target=remove_file)
    cleanup_thread.daemon = True
    cleanup_thread.start()
    return send_file(
        file_path,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'OK',
        'message': 'Servidor Ponto Eletrônico funcionando',
        'model': 'Ponto Eletrônico - Minuano - Validação de Datas por Intervalo e Regex de Horários Aprimorada'
    })
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5003, debug=False)
