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

# Configuração do logger (removida, mas a importação de logging pode ser mantida se outras partes do sistema usarem)
# import logging
# logger = logging.getLogger(__name__) # Esta linha pode ser removida se não houver mais uso de logger

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
        self.last_inferred_date = None # Novo atributo para armazenar a última data inferida com sucesso
        # MOVIDO PARA AQUI: Definição do mapeamento de dias da semana
        self.day_map_pt_en = {
            'seg': 'Mon', 'ter': 'Tue', 'qua': 'Wed', 'qui': 'Thu',
            'sex': 'Fri', 'sab': 'Sat', 'dom': 'Sun'
        }

    def update_progress(self, current_step, total_steps, message):
        """Atualiza o progresso da tarefa"""
        if self.task_id:
            progress_percent = int((current_step / total_steps) * 100)
            task_progress[self.task_id].update({
                'progress': progress_percent,
                'message': message,
                'current_step': current_step,
                'total_steps': total_steps,
                'timestamp': datetime.now().isoformat()
            })

    def converter_pdf_imagens(self, pdf_path, pages_range=None, dpi=300):
        """Converte PDF para imagens"""
        try:
            self.update_progress(1, 10, "Convertendo PDF para imagens...")
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
            self.update_progress(2, 10, f"PDF convertido com sucesso. {len(imagens)} páginas encontradas.")
            return imagens
        except Exception as e:
            self.update_progress(2, 10, f"Erro ao converter PDF para imagens: {str(e)}")
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
        potential_day_vals = [] # Armazena inteiros de dias válidos (1-31)

        # Tenta converter a string original para um dia válido
        try:
            val = int(original_day_str)
            if 1 <= val <= 31:
                potential_day_vals.append(val)
        except ValueError:
            pass

        # Correção: '09X' -> '0X' (e.g., '098' -> '08')
        if len(original_day_str) == 3 and original_day_str.startswith('09'):
            try:
                corrected_day_str = '0' + original_day_str[2]
                val = int(corrected_day_str)
                if 1 <= val <= 31 and val not in potential_day_vals:
                    potential_day_vals.append(val)
            except ValueError:
                pass

        # Correção: '9X' -> '0X' (e.g., '93' -> '03', '98' -> '08')
        if len(original_day_str) == 2 and original_day_str.startswith('9'):
            try:
                corrected_day_str = '0' + original_day_str[1]
                val = int(corrected_day_str)
                if 1 <= val <= 31 and val not in potential_day_vals:
                    potential_day_vals.append(val)
            except ValueError:
                pass

        # Limpeza genérica: remove caracteres não-dígitos e tenta pegar os últimos 2 dígitos se for muito longo
        cleaned_day_str_raw = re.sub(r'[^\d]', '', original_day_str)
        if cleaned_day_str_raw:
            # Tenta os últimos 2 dígitos
            if len(cleaned_day_str_raw) >= 2:
                last_two = cleaned_day_str_raw[-2:]
                try:
                    val = int(last_two)
                    if 1 <= val <= 31 and val not in potential_day_vals:
                        potential_day_vals.append(val)
                except ValueError:
                    pass
            # Tenta os primeiros 2 dígitos (se houver mais de 2)
            if len(cleaned_day_str_raw) > 2:
                first_two = cleaned_day_str_raw[:2]
                try:
                    val = int(first_two)
                    if 1 <= val <= 31 and val not in potential_day_vals:
                        potential_day_vals.append(val)
                except ValueError:
                    pass
            # Tenta a string limpa se tiver 1 ou 2 dígitos e não foi adicionada
            if len(cleaned_day_str_raw) in [1, 2]:
                try:
                    val = int(cleaned_day_str_raw)
                    if 1 <= val <= 31 and val not in potential_day_vals:
                        potential_day_vals.append(val)
                except ValueError:
                    pass

        # Remove duplicatas e mantém a ordem de preferência
        unique_potential_days = sorted(list(set(potential_day_vals)), key=lambda x: potential_day_vals.index(x) if x in potential_day_vals else len(potential_day_vals))

        inferred_date = None
        # Tenta inferir a data usando cada dia potencial
        for day_val in unique_potential_days:
            current_date_iter = page_start_date
            while current_date_iter <= page_end_date:
                # CORREÇÃO AQUI: Usando self.day_map_pt_en
                if current_date_iter.day == day_val and current_date_iter.strftime('%a') == self.day_map_pt_en.get(day_of_week_abbr.lower(), ''):
                    inferred_date = current_date_iter
                    break
                current_date_iter += timedelta(days=1)
            if inferred_date:
                break

        # Lógica de inferência sequencial se a inferência direta falhou
        if not inferred_date and self.last_inferred_date:
            # Tenta o próximo dia após a última data inferida
            next_expected_date = self.last_inferred_date + timedelta(days=1)
            # Verifica se o dia da semana da próxima data esperada corresponde ao da linha atual
            # E se a próxima data esperada está dentro do intervalo da página
            # CORREÇÃO AQUI: Usando self.day_map_pt_en
            if next_expected_date.strftime('%a') == self.day_map_pt_en.get(day_of_week_abbr.lower(), '') and \
               page_start_date <= next_expected_date <= page_end_date:
                inferred_date = next_expected_date
            else:
                pass

        if inferred_date:
            self.last_inferred_date = inferred_date # Atualiza a última data inferida com sucesso
            return inferred_date.strftime('%d/%m/%Y')
        else:
            return None

    def detectar_inicio_tabela(self, linhas):
        """
        Detecta onde a tabela de ponto começa, procurando por uma linha que
        contenha um dia do mês e dia da semana.
        """
        date_day_pattern = r'^\s*\d+\s+(?:Sab|Dom|Seg|Ter|Qua|Qui|Sex)' # Alterado para \d+
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

        # Reinicia a última data inferida para cada processamento de página
        self.last_inferred_date = None

        for i in range(indice_inicio, indice_fim):
            linha = linhas[i].strip()
            if not linha:
                continue

            line_segment = linha
            data = None
            # CORREÇÃO AQUI: Mudado de \d{1,2} para \d+ para capturar qualquer número de dígitos
            date_match_dd_day = re.match(r'^\s*(\d+)\s+([A-Za-z]{3})', linha, re.IGNORECASE)
            if date_match_dd_day:
                day_str = date_match_dd_day.group(1)
                day_of_week_abbr = date_match_dd_day.group(2)
                # Passa a última data inferida para a função de inferência
                inferred_date_str = self._inferir_data_com_dia_semana(day_str, day_of_week_abbr, page_start_date, page_end_date)
                if inferred_date_str:
                    data = inferred_date_str
            else:
                date_match_dd_mm = re.match(r'^\s*(\d{1,2}/\d{1,2})', linha)
                if date_match_dd_mm:
                    data_str = date_match_dd_mm.group(1)
                    inferred_date_str = self._inferir_ano_data(data_str, page_start_date, page_end_date)
                    if inferred_date_str:
                        data = inferred_date_str

            if data: # Só processa a linha se a data foi inferida com sucesso
                horarios_finais = []
                # 1. Extrair a seção de tempos após o código de turno/registro
                codes_pattern_and_rest = re.search(r'(?:\d{3,4}\s+[A-Za-z]{2,3})\s*(.*)', line_segment)
                times_section = ""
                if codes_pattern_and_rest:
                    times_section = codes_pattern_and_rest.group(1).strip()
                else:
                    times_section = line_segment
                # 2. Extrair horários brutos que terminam com um caractere alfanumérico (batidas reais)
                horarios_brutos_com_sufixo = re.findall(r'(\d{1,2}:\d{2})[A-Za-z0-9]', times_section)
                horarios_brutos = [h for h in horarios_brutos_com_sufixo]
                valid_punches = [h for h in horarios_brutos if h != '00:00']

                # 3. Lógica para determinar se é "Folga/Férias" ou um dia de trabalho
                # Considera "Folga/Férias" APENAS se a linha contém as palavras E não há batidas válidas.
                if re.search(r'Folga|Ferias', linha, re.IGNORECASE) and not valid_punches:
                    horarios_finais = ["0", "0", "0", "0"]
                else:
                    # Lógica de seleção: primeiros 2 e últimos 2, ou preenchimento sequencial
                    final_punches = ["0", "0", "0", "0"]
                    num_valid_punches = len(valid_punches)
                    if num_valid_punches >= 4:
                        # Se 4 ou mais punches, pega os 2 primeiros e os 2 últimos
                        final_punches[0] = valid_punches[0]
                        final_punches[1] = valid_punches[1]
                        final_punches[2] = valid_punches[-2] # Penúltimo
                        final_punches[3] = valid_punches[-1] # Último
                    elif num_valid_punches == 3:
                        # Se 3 punches, pega sequencialmente (1ª Entrada, 1ª Saída, 2ª Entrada)
                        final_punches[0] = valid_punches[0]
                        final_punches[1] = valid_punches[1]
                        final_punches[2] = valid_punches[2]
                    elif num_valid_punches == 2:
                        # Se 2 punches, pega sequencialmente (1ª Entrada, 1ª Saída)
                        final_punches[0] = valid_punches[0]
                        final_punches[1] = valid_punches[1]
                    elif num_valid_punches == 1:
                        # Se 1 punch, pega como 1ª Entrada
                        final_punches[0] = valid_punches[0]
                    # Se num_valid_punches == 0, final_punches permanece ["0", "0", "0", "0"]
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

    def processar_pagina(self, imagem, num_pagina, total_imagens):
        """Processa uma página completa usando OCR direto"""
        self.update_progress(3 + int((num_pagina / total_imagens) * 5), 10, f"Processando página {num_pagina}...")
        texto_completo = self.extrair_texto_completo(imagem)
        if not texto_completo:
            return pd.DataFrame()
        page_start_date, page_end_date = self._extrair_intervalo_datas_cabecalho(texto_completo)
        dados_extraidos = self.processar_texto_ponto(texto_completo, page_start_date, page_end_date)
        if dados_extraidos:
            df = pd.DataFrame(dados_extraidos)
            df['Pagina'] = num_pagina
            return df
        else:
            return pd.DataFrame()

    def processar_pdf_completo(self, pdf_path, pages_range=None):
        """Processa PDF completo"""
        self.update_progress(0, 10, "Iniciando processamento...")
        imagens = self.converter_pdf_imagens(pdf_path, pages_range)
        if not imagens:
            self.update_progress(10, 10, "Erro: Não foi possível converter o PDF.")
            return []

        todas_tabelas = []
        total_imagens = len(imagens)
        for i, imagem in enumerate(imagens, 1):
            if pages_range and '-' in pages_range:
                start_page = int(pages_range.split('-')[0])
                num_pagina_real = start_page + i - 1
            else:
                num_pagina_real = i
            df_pagina = self.processar_pagina(imagem, num_pagina_real, total_imagens)
            if not df_pagina.empty:
                todas_tabelas.append(df_pagina)

        self.update_progress(9, 10, "Consolidando dados extraídos...")
        if todas_tabelas:
            df_consolidado = pd.concat(todas_tabelas, ignore_index=True)
            df_consolidado['Data_dt'] = pd.to_datetime(df_consolidado['Data'], format='%d/%m/%Y', errors='coerce')
            df_consolidado.drop_duplicates(subset=['Data_dt', '1ª Entrada', '1ª Saída', '2ª Entrada', '2ª Saída'], keep='first', inplace=True)
            df_consolidado.sort_values(by='Data_dt', inplace=True)
            df_consolidado.drop(columns=['Data_dt'], inplace=True)
            self.update_progress(10, 10, "Processamento concluído com sucesso!")
            return [df_consolidado]
        else:
            self.update_progress(10, 10, "Nenhum dado foi extraído.")
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
            return

        extrator.update_progress(10, 10, "Gerando arquivo CSV...")
        output = BytesIO()
        df_final = tabelas[0]

        df_final['Data'] = pd.to_datetime(df_final['Data'], format='%d/%m/%Y', errors='coerce')
        weekday_map = {
            'Mon': 'Seg', 'Tue': 'Ter', 'Wed': 'Qua', 'Thu': 'Qui',
            'Fri': 'Sex', 'Sab': 'Sab', 'Sun': 'Dom'
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
        task_progress[task_id].update({
            'status': 'completed',
            'file_path': temp_file_path,
            'filename': filename,
            'progress': 100,
            'message': 'Arquivo processado com sucesso!'
        })
    except Exception as e:
        task_progress[task_id].update({
            'status': 'error',
            'error': str(e),
            'progress': 0,
            'message': f'Erro durante o processamento: {str(e)}'
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

        task_progress[task_id] = {
            'progress': 0,
            'message': 'Tarefa iniciada...',
            'status': 'processing',
            'current_step': 0,
            'total_steps': 10,
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
