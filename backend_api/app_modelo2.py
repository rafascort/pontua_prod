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
import threading
import time
import uuid
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

import platform
if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

task_progress = {}

class ExtractorPontoEletronico:
    def __init__(self, model_type='2', task_id=None, debug_mode=False):
        self.model_type = model_type
        self.config_ocr = r'--oem 3 --psm 6 -l por'
        self.task_id = task_id
        self.debug_mode = debug_mode
        self.dias_semana_map = {
            'Mon': 'Seg', 'Tue': 'Ter', 'Wed': 'Qua', 'Thu': 'Qui',
            'Fri': 'Sex', 'Sat': 'Sab', 'Sun': 'Dom'
        }
        self.periodo_inicio = None
        self.periodo_fim = None

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
            texto = pytesseract.image_to_string(gray, config=self.config_ocr)
            return texto
        except Exception as e:
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
        processed_dates = set()

        while current_date_tracker <= self.periodo_fim:
            # ALTERAÇÃO AQUI: Mudar o separador de '.' para '/'
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
                        # Processa os horários
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
                # Se a data não foi encontrada, adiciona uma entrada padrão
                dados_linha = {
                    'Dia': data_str,
                    'Dia_Semana': self.dias_semana_map.get(current_date_tracker.strftime('%a'), ''),
                    'Entrada1': '0',
                    'Saida1': '0',
                    'Entrada2': '0',
                    'Saida2': '0'
                }
                dados_extraidos.append(dados_linha)

            # Avança para o próximo dia
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
        self.update_progress(0, 10, "Iniciando processamento...")
        imagens = self.converter_pdf_imagens(pdf_path, pages_range)
        if not imagens:
            self.update_progress(10, 10, "Erro: Não foi possível converter o PDF.")
            return []

        todas_tabelas = []
        total_imagens = len(imagens)
        for i, imagem in enumerate(imagens, 1):
            current_progress = 3 + int((i / total_imagens) * 5)
            self.update_progress(current_progress, 10, f"Processando página {i} de {total_imagens}...")

            if pages_range and '-' in pages_range:
                start_page = int(pages_range.split('-')[0])
                num_pagina_real = start_page + i - 1
            else:
                num_pagina_real = i

            df_pagina = self.processar_pagina(imagem, num_pagina_real)
            if not df_pagina.empty:
                todas_tabelas.append(df_pagina)

        self.update_progress(9, 10, "Consolidando dados extraídos...")
        if todas_tabelas:
            df_consolidado = pd.concat(todas_tabelas, ignore_index=True)
            self.update_progress(10, 10, "Processamento concluído com sucesso!")
            return [df_consolidado]
        else:
            self.update_progress(10, 10, "Nenhum dado foi extraído.")
            return []

def process_pdf_background(task_id, pdf_path, pages, model_type):
    """Processa o PDF em background"""
    try:
        extrator = ExtractorPontoEletronico(model_type, task_id, debug_mode=False) # Debug desligado
        tabelas = extrator.processar_pdf_completo(pdf_path, pages)

        if not tabelas:
            task_progress[task_id]['status'] = 'error'
            task_progress[task_id]['error'] = 'Nenhuma tabela foi encontrada no PDF'
            return

        extrator.update_progress(10, 10, "Gerando arquivo CSV...") # Alterado para CSV
        output = BytesIO()
        df_final = tabelas[0]

        colunas_finais = ['Dia', 'Dia_Semana', 'Entrada1', 'Saida1', 'Entrada2', 'Saida2']
        for col in colunas_finais:
            if col not in df_final.columns:
                df_final[col] = "0"
        df_final = df_final[colunas_finais]
        df_final = df_final.fillna("0")
        df_final = df_final.replace("", "0")

        # Salva o DataFrame como CSV no BytesIO
        df_final.to_csv(output, index=False, sep=';', encoding='utf-8') # Usando ';' como separador para compatibilidade BR
        output.seek(0)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'BRF_ponto_extraido_{timestamp}.csv' # Alterado para .csv
        temp_file_path = os.path.join(tempfile.gettempdir(), f"{task_id}.csv") # Alterado para .csv
        with open(temp_file_path, 'wb') as f:
            f.write(output.getvalue())

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
    """Endpoint principal para processar PDF - Versão com monitoramento"""
    try:
        if 'pdf_file' not in request.files:
            return jsonify({'error': 'Nenhum arquivo PDF foi enviado'}), 400

        file = request.files['pdf_file']
        pages = request.form.get('pages', '')
        model_type = request.form.get('model_type', '2')

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
    """Endpoint para consultar o progresso de uma tarefa"""
    if task_id not in task_progress:
        return jsonify({'error': 'Tarefa não encontrada'}), 404
    return jsonify(task_progress[task_id])

@app.route('/download/<task_id>', methods=['GET'])
def download_result(task_id):
    """Endpoint para baixar o resultado processado"""
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
        time.sleep(2) # Pequeno atraso para garantir que o download foi iniciado
        try:
            os.unlink(file_path)
            del task_progress[task_id]
        except Exception as e:
            pass # Ignora erros se o arquivo já foi removido ou não existe

    cleanup_thread = threading.Thread(target=remove_file)
    cleanup_thread.daemon = True
    cleanup_thread.start()

    return send_file(
        file_path,
        mimetype='text/csv', # Alterado para mimetype de CSV
        as_attachment=True,
        download_name=filename
    )

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'OK',
        'message': 'Servidor Ponto Eletrônico (MODELO 2 - BRF) funcionando',
        'model': 'BRF Ponto Eletrônico - Com validação de horários e monitoramento (Saída CSV)' # Adicionado indicação de saída CSV
    })

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001, debug=False) # IMPORTANTE: Rodar na porta 5001

