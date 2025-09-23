# /opt/pontua/AutoPonto/backend_api/extractor_pontomais.py
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
    def __init__(self, model_type='3', job=None):
        self.model_type = model_type
        self.config_ocr = r'--oem 3 --psm 6 -l por'
        self.job = job
        self.column_end_pos = -1 # Posição de corte para a busca de horários (antes de 'Crédito'/'Débito')

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
            text = pytesseract.image_to_string(gray, config=self.config_ocr)
            return text
        except Exception as e:
            print(f"Erro ao extrair texto com OCR: {e}")
            return ""

    def _extrair_intervalo_datas_cabecalho(self, text):
        """
        Extrai o intervalo de datas do documento (ex: "De DD/MM/YYYY a DD/MM/YYYY")
        do texto OCR completo, geralmente do cabeçalho da página.
        Retorna (start_date, end_date) como objetos datetime. Se não encontrado,
        retorna um intervalo muito amplo (1900-2100) para desativar a filtragem por data.
        """
        date_range_pattern = r'(?:De|From|Período:|Period:)\s*(\d{1,2}/\d{1,2}/\d{4})\s*(?:a|to|até)\s*(\d{1,2}/\d{1,2}/\d{4})'
        match = re.search(date_range_pattern, text, re.IGNORECASE)
        if match:
            start_date_str = match.group(1)
            end_date_str = match.group(2)
            try:
                start_date = datetime.strptime(start_date_str, '%d/%m/%Y')
                end_date = datetime.strptime(end_date_str, '%d/%m/%Y')
                return start_date, end_date
            except ValueError:
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
        return datetime(1900, 1, 1), datetime(2100, 12, 31)

    def detectar_inicio_tabela(self, linhas):
        """
        Detecta onde a tabela de ponto começa e define a posição de corte
        para a busca de horários, ignorando colunas irrelevantes.
        """
        header_pattern = r'^\s*Data\s+(?:Dia_Semana\s*)?1[aºª]?\s*Entrada'
        self.column_end_pos = -1 # Reset para cada nova tabela
        for i, linha in enumerate(linhas):
            if re.search(header_pattern, linha, re.IGNORECASE):
                forbidden_columns_patterns = [
                    r'\bCrédito\b', r'\bDébito\b', r'\bH\.\s*intervalo\b',
                    r'\bHoras\s*normais\b', r'\bH\.E\.\s*1\b', r'\bH\.E\.\s*2\b',
                    r'\bAdicional\s*noturno\b', r'\bSaldo\b', r'\bMotivo/Observação\b'
                ]
                min_pos = len(linha)
                for pattern in forbidden_columns_patterns:
                    match = re.search(pattern, linha, re.IGNORECASE)
                    if match:
                        min_pos = min(min_pos, match.start())
                if min_pos < len(linha):
                    self.column_end_pos = min_pos
                return i
        return 0

    def detectar_fim_tabela(self, linhas, indice_inicio):
        """Detecta onde a tabela de ponto termina para o formato 'pontomais'"""
        for i in range(indice_inicio, len(linhas)):
            linha = linhas[i].strip()
            if re.search(r'^\s*TOTAL\s+(?:DE\s+)?Horas\b', linha, re.IGNORECASE):
                return i
            if i > indice_inicio + 10 and re.search(r'\b(assinatura|funcionário|chefia|visto|preparado por)\b', linha, re.IGNORECASE):
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
        final_horarios = [entrada1, saida1, entrada2, saida2]
        return final_horarios

    def _parse_time(self, time_str):
        """
        Helper para parsear uma string de tempo, aceitando HH:MM ou HHHH (para correção de OCR).
        Retorna HH:MM formatado ou "0" se inválido.
        """
        time_str = time_str.strip()
        h, m = -1, -1
        if ':' in time_str:
            try:
                h, m = map(int, time_str.split(':'))
            except ValueError:
                pass
        elif len(time_str) == 4 and time_str.isdigit():
            try:
                h = int(time_str[:2])
                m = int(time_str[2:])
            except ValueError:
                pass
        if 0 <= h <= 23 and 0 <= m <= 59:
            if h == 0 and m == 0:
                return "0"
            return f"{h:02d}:{m:02d}"
        return "0"

    def processar_texto_ponto(self, texto, page_start_date, page_end_date):
        """Processa o texto extraído para encontrar dados de ponto para o formato 'pontomais'"""
        linhas = texto.split('\n')
        indice_inicio = self.detectar_inicio_tabela(linhas)
        indice_fim = self.detectar_fim_tabela(linhas, indice_inicio)
        linhas_tabela = linhas[indice_inicio:indice_fim]
        dados_extraidos = []
        for idx, linha in enumerate(linhas_tabela):
            linha_original = linha.strip()
            if not linha_original:
                continue
            data_match = re.search(r'^\s*(?:\w{2,}[.,]?\s*)?(\d{1,2}/\d{1,2}/\d{4})', linha_original)
            if data_match:
                data_full_match_str = data_match.group(0)
                data_str = data_match.group(1)
                try:
                    current_line_date = datetime.strptime(data_str, '%d/%m/%Y')
                    if not (page_start_date <= current_line_date <= page_end_date):
                        continue
                except ValueError:
                    continue
                dia_semana_map = {
                    0: 'Seg', 1: 'Ter', 2: 'Qua', 3: 'Qui', 4: 'Sex', 5: 'Sab', 6: 'Dom'
                }
                dia_semana = dia_semana_map.get(current_line_date.weekday(), '')
                current_search_pos = linha_original.find(data_full_match_str) + len(data_full_match_str)
                search_end_limit = len(linha_original)
                if self.column_end_pos != -1 and self.column_end_pos > current_search_pos:
                    search_end_limit = self.column_end_pos
                horarios_extraidos_seq = []
                time_pattern_regex = r'(\d{1,2}:[0-5]\d|\d{4})'
                for i in range(4):
                    if current_search_pos >= search_end_limit:
                        horarios_extraidos_seq.append("0")
                        continue
                    match_time = re.search(time_pattern_regex, linha_original[current_search_pos:search_end_limit])
                    if match_time:
                        time_str = match_time.group(1)
                        parsed_time = self._parse_time(time_str)
                        horarios_extraidos_seq.append(parsed_time)
                        current_search_pos += match_time.end()
                    else:
                        horarios_extraidos_seq.append("0")
                while len(horarios_extraidos_seq) < 4:
                    horarios_extraidos_seq.append("0")
                horarios_validos_parsed = horarios_extraidos_seq[:4]
                non_zero_parsed_times_count = sum(1 for h in horarios_validos_parsed if h != "0")
                palavras_que_zeram_tudo = [
                    'FOLGA', 'FER', 'INTEGRAÇÃO', 'INTERAÇÃO',
                    'ATESTADO', 'MÉDICO', 'FALTA', 'LICENÇA', 'FÉRIAS', 'DISPENSA',
                    'AUSÊNCIA JUSTIFICADA', 'AUSENCIA JUSTIFICADA', 'ABONO'
                ]
                horarios_finais = []
                matched_zero_word = None
                for palavra in palavras_que_zeram_tudo:
                    if palavra in linha_original.upper():
                        matched_zero_word = palavra
                        break
                if matched_zero_word and non_zero_parsed_times_count <= 1:
                    horarios_finais = ["0", "0", "0", "0"]
                else:
                    horarios_finais = self.validar_horarios(horarios_validos_parsed)
                if horarios_finais[0] != "0" and horarios_finais[1] != "0":
                    try:
                        entrada1_dt = datetime.strptime(horarios_finais[0], '%H:%M')
                        saida1_dt = datetime.strptime(horarios_finais[1], '%H:%M')
                        # Correção para casos onde a saída é no dia seguinte e OCR lê 01:xx como 1:xx
                        if saida1_dt.hour == 1 and 5 <= entrada1_dt.hour <= 10 and saida1_dt < entrada1_dt:
                            horarios_finais[1] = f"11:{saida1_dt.minute:02d}"
                    except ValueError:
                        pass
                while len(horarios_finais) < 4:
                    horarios_finais.append("0")
                horarios_finais = horarios_finais[:4]
                dados_linha = {
                    'Dia': data_str, # Padronizado para 'Dia'
                    'Dia_Semana': dia_semana, # Adicionado Dia_Semana
                    'Entrada1': horarios_finais[0], # Padronizado
                    'Saida1': horarios_finais[1], # Padronizado
                    'Entrada2': horarios_finais[2], # Padronizado
                    'Saida2': horarios_finais[3] # Padronizado
                }
                dados_extraidos.append(dados_linha)
            else:
                pass # Linha sem data válida no início é ignorada.
        return dados_extraidos

    def processar_pagina(self, imagem, num_pagina):
        """Processa uma página completa usando OCR direto"""
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
        self.update_progress(0, 1, "Iniciando processamento e conversão de PDF...")
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
            df_consolidado['Dia_dt'] = pd.to_datetime(df_consolidado['Dia'], format='%d/%m/%Y', errors='coerce')
            df_consolidado.drop_duplicates(subset=['Dia_dt', 'Entrada1', 'Saida1', 'Entrada2', 'Saida2'], keep='first', inplace=True)
            df_consolidado.sort_values(by='Dia_dt', inplace=True)
            df_consolidado.drop(columns=['Dia_dt'], inplace=True)
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
        filename = f'PontoMais_ponto_extraido_{timestamp}.csv'
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
            print(f"PDF temporário {pdf_path} removido pelo worker.") # Adicionado print para depuração
