from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
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
import threading
import time
import uuid

app = Flask(__name__)
CORS(app)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Armazenamento em memória para o progresso das tarefas
task_progress = {}

class ExtractorPontoEletronico:
    def __init__(self, model_type='1', task_id=None):
        self.model_type = model_type
        self.config_ocr = r'--oem 3 --psm 6 -l por'
        self.task_id = task_id

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
        except Exception:
            self.update_progress(2, 10, "Erro ao converter PDF para imagens.")
            return []

    def extrair_texto_completo(self, imagem):
        """Extrai todo o texto da página usando OCR"""
        try:
            img_cv = cv2.cvtColor(np.array(imagem), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            gray = cv2.bilateralFilter(gray, 9, 75, 75)
            return pytesseract.image_to_string(gray, config=self.config_ocr)
        except Exception:
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
        # Garantir que temos exatamente 4 posições
        while len(horarios_validos) < 4:
            horarios_validos.append("0")
        horarios_validos = horarios_validos[:4]

        # Contar horários válidos (diferentes de "0")
        horarios_nao_zero = [h for h in horarios_validos if h != "0"]

        # Regra 1: Se apenas 1 horário, zerar todos
        if len(horarios_nao_zero) == 1:
            return ["0", "0", "0", "0"]

        # Aplicar as regras de validação
        entrada1, saida1, entrada2, saida2 = horarios_validos

        # Se tem entrada1 mas não tem saida1, zerar ambos
        if entrada1 != "0" and saida1 == "0":
            entrada1 = "0"
            saida1 = "0"

        # Se tem saida1 mas não tem entrada1, zerar saida1
        if entrada1 == "0" and saida1 != "0":
            saida1 = "0"

        # Se tem entrada2 mas não tem saida2, zerar ambos
        if entrada2 != "0" and saida2 == "0":
            entrada2 = "0"
            saida2 = "0"

        # Se tem saida2 mas não tem entrada2, zerar saida2
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

                # Buscar dia da semana
                dia_semana = ""
                for dia in dias_semana:
                    if dia in linha:
                        dia_semana = dia
                        break

                if not dia_semana:
                    if any(variacao in linha for variacao in ['Sáb', 'SAB', 'sab', 'Sabado', 'sábado']):
                        dia_semana = 'Sab'

                # Definir área de busca dos horários
                pos_data = linha.find(data)
                inicio_busca = pos_data + len(data)

                if dia_semana and dia_semana in linha:
                    pos_dia = linha.find(dia_semana)
                    if pos_dia > pos_data:
                        inicio_busca = pos_dia + len(dia_semana)

                substring_horarios = linha[inicio_busca:]
                linha_upper = substring_horarios.upper()
                pos_fim = len(substring_horarios)

                # Procurar colunas proibidas para delimitar fim
                for coluna in colunas_proibidas:
                    coluna_upper = coluna.upper()
                    if coluna_upper in linha_upper:
                        pos_temp = linha_upper.find(coluna_upper)
                        if pos_temp >= 0 and pos_temp < pos_fim:
                            pos_fim = pos_temp
                            break

                parte_horarios = substring_horarios[:pos_fim]

                # Buscar horários
                horarios = re.findall(r'\b([0-2]?\d:[0-5]\d)\b', parte_horarios)

                # Processar horários
                horarios_validos = []
                for h in horarios[:4]: # Máximo 4 horários
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

                # Verificar dias especiais primeiro
                palavras_especiais = ['FOLG', 'COMP', 'FER', 'INTEGRAÇÃO', 'INTERAÇÃO',
                                    'ATESTADO', 'MÉDICO', 'FALTA', 'LICENÇA', 'FÉRIAS']
                if any(palavra in linha.upper() for palavra in palavras_especiais):
                    horarios_validos = ["0", "0", "0", "0"]
                else:
                    # Aplicar validação de horários
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
        self.update_progress(0, 10, "Iniciando processamento...")

        imagens = self.converter_pdf_imagens(pdf_path, pages_range)
        if not imagens:
            self.update_progress(10, 10, "Erro: Não foi possível converter o PDF.")
            return []

        todas_tabelas = []
        total_imagens = len(imagens)

        for i, imagem in enumerate(imagens, 1):
            # Calcular progresso (3-8 dos 10 steps para processamento das páginas)
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

# Função para processar em background
def process_pdf_background(task_id, pdf_path, pages, model_type):
    """Processa o PDF em background"""
    try:
        extrator = ExtractorPontoEletronico(model_type, task_id)
        tabelas = extrator.processar_pdf_completo(pdf_path, pages)

        if not tabelas:
            task_progress[task_id]['status'] = 'error'
            task_progress[task_id]['error'] = 'Nenhuma tabela foi encontrada no PDF'
            return

        # Gerar arquivo Excel
        extrator.update_progress(10, 10, "Gerando arquivo Excel...")
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_final = tabelas[0]

            colunas_finais = ['Dia', 'Dia_Semana', 'Entrada1', 'Saida1', 'Entrada2', 'Saida2']
            for col in colunas_finais:
                if col not in df_final.columns:
                    df_final[col] = "0"

            df_final = df_final[colunas_finais]
            df_final = df_final.fillna("0")
            df_final = df_final.replace("", "0")

            df_final.to_excel(writer, sheet_name='Ponto_Extraido', index=False)

        output.seek(0)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'JBS_ponto_extraido_{timestamp}.xlsx'

        # Salvar arquivo temporário
        temp_file_path = os.path.join(tempfile.gettempdir(), f"{task_id}.xlsx")
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
        # Limpar arquivo PDF temporário
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
        model_type = request.form.get('model_type', '1')

        if file.filename == '':
            return jsonify({'error': 'Nenhum arquivo selecionado'}), 400

        # Gerar ID único para a tarefa
        task_id = str(uuid.uuid4())

        # Salvar arquivo temporário
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            file.save(tmp_file.name)
            pdf_path = tmp_file.name

        # Inicializar progresso
        task_progress[task_id] = {
            'progress': 0,
            'message': 'Tarefa iniciada...',
            'status': 'processing',
            'current_step': 0,
            'total_steps': 10,
            'timestamp': datetime.now().isoformat()
        }

        # Iniciar processamento em background
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
        time.sleep(2)  # Aguardar um pouco antes de remover
        try:
            os.unlink(file_path)
            del task_progress[task_id]  # Remover da memória também
        except:
            pass

    # Programar remoção do arquivo
    cleanup_thread = threading.Thread(target=remove_file)
    cleanup_thread.daemon = True
    cleanup_thread.start()

    return send_file(
        file_path,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'OK',
        'message': 'Servidor JBS Ponto funcionando',
        'model': 'JBS Ponto Eletrônico - Com validação de horários e monitoramento'
    })

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)