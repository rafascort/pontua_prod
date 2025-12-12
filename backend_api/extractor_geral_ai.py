# /opt/pontua/AutoPonto/backend_api/extractor_geral_ai.py

import os
import tempfile
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta
from rq import get_current_job
from google.cloud import documentai_v1 as documentai
from google.cloud import storage
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
import re
import traceback
from pdf2image import convert_from_path
import pytesseract
import platform
from PIL import Image

# Configuração do Tesseract
if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

class ExtractorGeralAI:
    def __init__(self, model_type='6', job=None):
        self.model_type = model_type
        self.job = job
        self.project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        self.location = os.getenv('DOCAI_PROCESSOR_LOCATION')
        self.processor_id = os.getenv('DOCAI_PROCESSOR_ID')
        self.gcs_bucket_name = os.getenv('GCS_BUCKET_NAME')
        self.storage_client = storage.Client()
        self.client = documentai.DocumentProcessorServiceClient(
            client_options={"api_endpoint": f"{self.location}-documentai.googleapis.com"}
        )
        self.processor_name = self.client.processor_path(self.project_id, self.location, self.processor_id)

    def update_progress(self, current, total, message, status='processing', extra_info=None):
        if self.job:
            progress = int((current / total) * 100) if total > 0 else 0
            meta_update = {
                'progress': progress, 'message': message, 'current_step': current,
                'total_steps': total, 'status': status, 'timestamp': datetime.now().isoformat()
            }
            if extra_info:
                meta_update.update(extra_info)
            self.job.meta.update(meta_update)
            self.job.save_meta()

    def extract_period_from_page(self, pdf_path, page_idx):
        try:
            images = convert_from_path(pdf_path, dpi=300, first_page=page_idx + 1, last_page=page_idx + 1)
            if not images: return None
            image = images[0]
            width, height = image.size
            top_section = image.crop((0, 0, width, height * 0.3)) 
            config_ocr_header = r'--oem 3 --psm 6 -l por'
            text = pytesseract.image_to_string(top_section, lang='por', config=config_ocr_header)
            if not text: return None
            for line in text.splitlines():
                dates_found = re.findall(r'\b(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\b', line)
                if len(dates_found) >= 2:
                    try:
                        start_date_str = dates_found[0].replace('.', '/').replace('-', '/')
                        end_date_str = dates_found[1].replace('.', '/').replace('-', '/')
                        try:
                            start_date = datetime.strptime(start_date_str, '%d/%m/%Y')
                            end_date = datetime.strptime(end_date_str, '%d/%m/%Y')
                        except ValueError:
                            start_date = datetime.strptime(start_date_str, '%d/%m/%y')
                            end_date = datetime.strptime(end_date_str, '%d/%m/%y')
                        return {'start_date': start_date.strftime('%d/%m/%Y'), 'end_date': end_date.strftime('%d/%m/%Y')}
                    except ValueError:
                        continue
            return None
        except Exception as e:
            print(f"[LOG][ERRO] Erro ao extrair período da página {page_idx + 1}: {e}")
            return None

    def split_pdf_and_extract_periods(self, pdf_path, page_range):
        try:
            reader = PdfReader(pdf_path, strict=False)
            total_pdf_pages = len(reader.pages)
        except PdfReadError as e:
            raise ValueError(f"PDF corrompido ou inválido: {str(e)}")
        
        page_indices = []
        if page_range:
            parts = page_range.split('-')
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                start_page = int(parts[0]) - 1; end_page = int(parts[1])
                page_indices = list(range(start_page, min(end_page, total_pdf_pages)))
            elif len(parts) == 1 and parts[0].isdigit():
                page_num = int(parts[0]) - 1
                if 0 <= page_num < total_pdf_pages: page_indices = [page_num]
        else:
            page_indices = list(range(total_pdf_pages))
        if not page_indices: raise ValueError("Nenhuma página válida para processar.")
        
        pages_info = []
        for idx, page_idx in enumerate(page_indices):
            self.update_progress(idx + 1, len(page_indices), f"Lendo cabeçalho da página {page_idx + 1}...", status='processing')
            period = self.extract_period_from_page(pdf_path, page_idx)
            pages_info.append({'page_number': page_idx + 1, 'page_index': page_idx, 'period': period})
        return pages_info

    def process_document_page_sync(self, pdf_path, page_idx):
        try:
            images = convert_from_path(pdf_path, dpi=300, first_page=page_idx + 1, last_page=page_idx + 1)
            if not images: return []
            image = images[0]
            image_bytes_io = BytesIO()
            image.save(image_bytes_io, format='JPEG', quality=95)
            image_bytes = image_bytes_io.getvalue()
            
            raw_document = documentai.RawDocument(content=image_bytes, mime_type='image/jpeg')
            request = documentai.ProcessRequest(name=self.processor_name, raw_document=raw_document, skip_human_review=True)
            result = self.client.process_document(request=request)
            return result.document.entities
        except Exception as e:
            print(f"[LOG][ERRO] Erro ao processar página {page_idx + 1} na IA: {e}")
            return []

    def process_pages_sync(self, pdf_path, pages_with_periods):
        pages_data = {}
        total_ai_pages = len(pages_with_periods)
        self.update_progress(1, 3, "Iniciando processamento IA...", extra_info={'ai_processing': True, 'ai_total_pages': total_ai_pages, 'ai_current_page': 0})
        for idx, page_info in enumerate(pages_with_periods):
            page_idx = page_info['page_index']
            self.update_progress(1, 3, f"Processando página {idx + 1} de {total_ai_pages}...", extra_info={'ai_processing': True, 'ai_total_pages': total_ai_pages, 'ai_current_page': idx + 1})
            entities = self.process_document_page_sync(pdf_path, page_idx)
            pages_data[idx] = {'entities': entities} 
        self.update_progress(2, 3, "Consolidando dados...", extra_info={'consolidating': True})
        return pages_data

    def format_ai_rows_by_order(self, entities):
        extracted_rows = []
        # A API DocumentAI já retorna entities geralmente na ordem de leitura (top-down)
        for entity in entities:
            if entity.type_.lower() == 'tabela_marcacoes' and entity.properties:
                row_data = {prop.type_.lower(): prop.mention_text.strip() for prop in entity.properties}
                extracted_rows.append({
                    'Dia_Str': row_data.get('data', '0'), 
                    'Dia_Semana_Str': row_data.get('dia_semana', ''),
                    'Entrada1': row_data.get('entrada1', '0'), 'Saida1': row_data.get('saida1', '0'),
                    'Entrada2': row_data.get('entrada2', '0'), 'Saida2': row_data.get('saida2', '0'),
                    'Entrada3': row_data.get('entrada3', '0'), 'Saida3': row_data.get('saida3', '0'),
                    'Entrada4': row_data.get('entrada4', '0'), 'Saida4': row_data.get('saida4', '0'),
                    'Entrada5': row_data.get('entrada5', '0'), 'Saida5': row_data.get('saida5', '0'),
                    'Entrada6': row_data.get('entrada6', '0'), 'Saida6': row_data.get('saida6', '0'),
                    'Entrada7': row_data.get('entrada7', '0'), 'Saida7': row_data.get('saida7', '0'),
                    'Entrada8': row_data.get('entrada8', '0'), 'Saida8': row_data.get('saida8', '0'),
                    'Entrada9': row_data.get('entrada9', '0'), 'Saida9': row_data.get('saida9', '0'),
                    'Entrada10': row_data.get('entrada10', '0'), 'Saida10': row_data.get('saida10', '0'),
                    'Entrada11': row_data.get('entrada11', '0'), 'Saida11': row_data.get('saida11', '0'),
                })
        return extracted_rows

def assign_dates_sequentially_strict(ai_rows, page_start_date):
    """
    Atribui datas estritamente pela ordem das linhas.
    Linha 0 = page_start_date
    Linha 1 = page_start_date + 1 dia
    ...
    Ignora completamente o conteúdo da coluna 'Dia' para fins de ordenação.
    """
    processed_rows = []
    
    day_map_pt = {0: "seg", 1: "ter", 2: "qua", 3: "qui", 4: "sex", 5: "sab", 6: "dom"}

    for i, row in enumerate(ai_rows):
        # Cálculo simples: Data inicial + indice da linha
        current_date = page_start_date + timedelta(days=i)
        
        # Sobrescreve a data e o dia da semana com o calculado
        row['Sort_Date'] = current_date
        row['Dia'] = current_date.strftime('%d/%m/%Y')
        row['Dia_Sema'] = day_map_pt.get(current_date.weekday(), "")
        
        processed_rows.append(row)

    return processed_rows

def normalize_time_format(value):
    if pd.isna(value) or str(value).strip() in ["0", "", "nan"]: return "0"
    value_str = str(value).strip().replace(' ', '').replace('\n', '').replace('\r', '').replace('\t', '')
    value_str = re.sub(r':+$', '', value_str)
    
    match = re.search(r'(\d{1,2})[^\d](\d{2})', value_str)
    if match: return f"{match.group(1).zfill(2)}:{match.group(2)}"
    if len(value_str) == 4 and value_str.isdigit(): return f"{value_str[:2]}:{value_str[2:]}"
    if len(value_str) == 3 and value_str.isdigit(): return f"0{value_str[0]}:{value_str[1:]}"
    if len(value_str) == 2 and value_str.isdigit(): return f"{value_str}:00"
    
    return "0"

def extract_periods_task(pdf_path, pages, user_id):
    job = get_current_job()
    if not job: return None
    job.meta['user_id'] = user_id; job.save_meta()
    
    print(f"[LOG] Usuário: {user_id} | A extrair períodos")

    extractor = ExtractorGeralAI(job=job)
    try:
        pages_info = extractor.split_pdf_and_extract_periods(pdf_path, pages)
        job.meta.update({'status': 'completed', 'result': pages_info, 'pdf_path': pdf_path}); job.save()
        return pages_info
    except Exception as e:
        print(f"[LOG][ERRO] {str(e)}")
        job.meta.update({'status': 'error', 'error': str(e)}); job.save()
        return None

def process_pdf_task(pdf_path, pages_with_periods_json, model_type, user_id):
    job = get_current_job()
    if not job: return None
    job.meta['user_id'] = user_id; job.save_meta()

    total_pages = len(pages_with_periods_json)
    print(f"[LOG] Usuário: {user_id} | Paginas: {total_pages}")

    pages_with_periods = []
    for p in pages_with_periods_json:
        if p.get('period') and p['period'].get('start_date') and p['period'].get('end_date'):
            try:
                p['start_date_obj'] = datetime.strptime(p['period']['start_date'], '%d/%m/%Y')
                p['end_date_obj'] = datetime.strptime(p['period']['end_date'], '%d/%m/%Y')
                pages_with_periods.append(p)
            except: pass

    if not pages_with_periods:
        job.meta.update({'status': 'error', 'error': 'Nenhuma página com período válido.'}); job.save()
        return None

    extractor = ExtractorGeralAI(model_type, job)
    try:
        pages_data = extractor.process_pages_sync(pdf_path, pages_with_periods)
        extractor.update_progress(2, 3, "Organizando dados sequencialmente...", extra_info={'consolidating': True})
        
        all_rows_data = []

        for idx, page_info in enumerate(pages_with_periods):
            page_order = idx
            start_date = page_info['start_date_obj']
            
            if page_order in pages_data and pages_data.get(page_order, {}).get('entities'):
                raw_rows = extractor.format_ai_rows_by_order(pages_data[page_order]['entities'])
                
                if raw_rows:
                    # Chamada para a função estrita (sem logs de debug)
                    processed_rows = assign_dates_sequentially_strict(raw_rows, start_date)
                    all_rows_data.extend(processed_rows)

        if not all_rows_data:
             raise Exception("A IA não retornou dados de marcação.")

        final_df = pd.DataFrame(all_rows_data)
        
        # Mantém a ordem exata da lista processada
        colunas_finais = ['Dia', 'Dia_Sema']
        for i in range(1, 12):
            colunas_finais.extend([f'Entrada{i}', f'Saida{i}'])
            
        for col in colunas_finais:
            if col not in final_df.columns: final_df[col] = "0"
            
        final_df = final_df[colunas_finais].fillna("0")
        
        time_cols = [c for c in colunas_finais if 'Entrada' in c or 'Saida' in c]
        for col in time_cols:
            final_df[col] = final_df[col].apply(normalize_time_format)
        
        output = BytesIO()
        final_df.to_csv(output, index=False, sep=';', encoding='utf-8-sig')
        output.seek(0)
        filename = f'Ponto_IA_extraido_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        temp_file_path = os.path.join(tempfile.gettempdir(), f"{job.id}.csv")
        with open(temp_file_path, 'wb') as f: f.write(output.getvalue())

        extractor.update_progress(3, 3, "Concluído!", status='completed')
        job.meta.update({'status': 'completed', 'file_path': temp_file_path, 'filename': filename})
        job.save()
        return temp_file_path
        
    except Exception as e:
        print(f"[LOG][ERRO] {traceback.format_exc()}")
        job.meta.update({'status': 'error', 'error': str(e)}); job.save()
        return None
    finally:
        if os.path.exists(pdf_path):
            try: os.unlink(pdf_path)
            except: pass
