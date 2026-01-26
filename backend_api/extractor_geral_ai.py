# /opt/pontua/AutoPonto/backend_api/extractor_geral_ai.py

import os
import tempfile
import pandas as pd
import logging
import random
import string
from io import BytesIO
from datetime import datetime, timedelta
from rq import get_current_job
from google.cloud import documentai_v1 as documentai
from google.cloud import storage
from pypdf import PdfReader
from pypdf.errors import PdfReadError
import re
import traceback
from pdf2image import convert_from_path
import pytesseract
import platform

# Configuração de Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ExtractorAI")

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
            top = images[0].crop((0, 0, images[0].size[0], images[0].size[1] * 0.3))
            text = pytesseract.image_to_string(top, lang='por')
            dates = re.findall(r'\b(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\b', text)
            if len(dates) >= 2:
                return {'start_date': dates[0].replace('.','/'), 'end_date': dates[1].replace('.','/')}
            return None
        except Exception:
            return None

    def split_pdf_and_extract_periods(self, pdf_path, page_range):
        reader = PdfReader(pdf_path)
        total = len(reader.pages)
        indices = list(range(total))
        if page_range:
            parts = str(page_range).split('-')
            if len(parts) == 2:
                indices = list(range(int(parts[0])-1, min(int(parts[1]), total)))
            elif parts[0].isdigit():
                indices = [int(parts[0])-1]
        
        pages_info = []
        for i in indices:
            self.update_progress(i + 1, len(indices), f"Analisando página {i+1}...")
            period = self.extract_period_from_page(pdf_path, i)
            pages_info.append({'page_number': i + 1, 'page_index': i, 'period': period})
        return pages_info

    def process_document_page_sync(self, pdf_path, page_idx):
        try:
            images = convert_from_path(pdf_path, dpi=300, first_page=page_idx + 1, last_page=page_idx + 1)
            img_io = BytesIO()
            images[0].save(img_io, format='JPEG', quality=95)
            raw_doc = documentai.RawDocument(content=img_io.getvalue(), mime_type='image/jpeg')
            request = documentai.ProcessRequest(name=self.processor_name, raw_document=raw_doc)
            result = self.client.process_document(request=request)
            return result.document.entities
        except Exception:
            return []

    def spatial_sort_entities(self, entities):
        def get_y(e):
            try: return e.page_anchor.page_refs[0].bounding_poly.normalized_vertices[0].y
            except: return 0
        rows = [e for e in entities if e.type_.lower() == 'tabela_marcacoes']
        return sorted(rows, key=get_y)

    def process_pages_sync(self, pdf_path, pages_with_periods):
        pages_data = {}
        total = len(pages_with_periods)
        for idx, page_info in enumerate(pages_with_periods):
            self.update_progress(1, 3, f"Processando página {idx+1}/{total}...", extra_info={'ai_total_pages': total, 'ai_current_page': idx+1})
            entities = self.process_document_page_sync(pdf_path, page_info['page_index'])
            pages_data[idx] = {'entities': entities}
        return pages_data

def normalize_time(val):
    if not val or val == '0' or val.lower() == 'nan': return "0"
    d = re.sub(r'[^\d]', '', str(val))
    if len(d) >= 4: return f"{d[:2]}:{d[2:4]}"
    if len(d) == 3: return f"0{d[0]}:{d[1:3]}"
    return "0"

def normalize_date(date_str, default_year):
    if not date_str: return None
    date_str = re.sub(r'[^\d/.-]', '', date_str).replace('.', '/').replace('-', '/')
    parts = date_str.split('/')
    if len(parts) >= 2:
        day = parts[0].zfill(2)
        month = parts[1].zfill(2)
        year = parts[2] if len(parts) == 3 else default_year
        if len(str(year)) == 2: year = f"20{year}"
        return f"{day}/{month}/{year}"
    return None

def extract_periods_task(pdf_path, pages, user_id):
    job = get_current_job()
    if not job: return None
    job.meta['user_id'] = user_id; job.save_meta()
    extractor = ExtractorGeralAI(job=job)
    try:
        res = extractor.split_pdf_and_extract_periods(pdf_path, pages)
        job.meta.update({'status': 'completed', 'result': res, 'pdf_path': pdf_path}); job.save()
        return res
    except Exception:
        return None

def process_pdf_task(pdf_path, pages_with_periods_json, model_type, user_id):
    job = get_current_job()
    if not job: return None
    job.meta['user_id'] = user_id; job.save_meta()
    extractor = ExtractorGeralAI(model_type, job)
    day_map_pt = {0: "seg", 1: "ter", 2: "qua", 3: "qui", 4: "sex", 5: "sab", 6: "dom"}
    
    try:
        valid_pages = []
        for p in pages_with_periods_json:
            p['start_dt'] = datetime.strptime(p['period']['start_date'], '%d/%m/%Y')
            valid_pages.append(p)

        global_start = valid_pages[0]['start_dt']
        global_end = datetime.strptime(valid_pages[-1]['period']['end_date'], '%d/%m/%Y')
        full_range = pd.date_range(start=global_start, end=global_end, freq='D')
        
        master_df = pd.DataFrame({
            'Dia': full_range.strftime('%d/%m/%Y'),
            'Dia_Sema': full_range.weekday.map(day_map_pt)
        })
        
        for i in range(1, 12): 
            master_df[f'Entrada{i}'] = "0"; master_df[f'Saida{i}'] = "0"

        pages_data = extractor.process_pages_sync(pdf_path, valid_pages)
        default_year = global_start.year
        
        # Rastreador de linha física para prever a data correta
        current_physical_row = 0

        for idx, page in enumerate(valid_pages):
            entities = pages_data.get(idx, {}).get('entities', [])
            sorted_entities = extractor.spatial_sort_entities(entities)
            
            for entity in sorted_entities:
                data = {p.type_.lower(): p.mention_text.strip() for p in entity.properties}
                
                data_ia = data.get('dia', data.get('data', None))
                data_normalizada = normalize_date(data_ia, default_year)
                
                target_idx = None
                
                # --- LÓGICA DE CORREÇÃO PARA O "BORRADO" DO FICHÁRIO ---
                if current_physical_row < len(master_df):
                    expected_date = master_df.at[current_physical_row, 'Dia']
                    
                    if data_normalizada:
                        ai_day = data_normalizada.split('/')[0].lstrip('0')
                        exp_day = expected_date.split('/')[0]
                        
                        # Se a IA leu só o final do dia (ex: leu '7' mas o esperado é '17')
                        # e o mês/ano são iguais aos esperados para essa linha física
                        if len(ai_day) == 1 and exp_day.endswith(ai_day) and data_normalizada[2:] == expected_date[2:]:
                            data_normalizada = expected_date
                    else:
                        # Se a IA não conseguiu ler data nenhuma, assume a data da linha física
                        data_normalizada = expected_date

                # Localiza a posição exata no calendário
                if data_normalizada:
                    idx_match = master_df.index[master_df['Dia'] == data_normalizada]
                    if not idx_match.empty:
                        target_idx = idx_match[0]

                # Se achou uma posição válida no calendário
                if target_idx is not None:
                    for k in range(1, 12):
                        e_val = normalize_time(data.get(f'entrada{k}', data.get(f'entrada_{k}', "0")))
                        s_val = normalize_time(data.get(f'saida{k}', data.get(f'saída{k}', "0")))
                        
                        # Preenche Entrada
                        if e_val != "0":
                            for col_k in range(1, 12):
                                if master_df.at[target_idx, f'Entrada{col_k}'] == "0":
                                    master_df.at[target_idx, f'Entrada{col_k}'] = e_val
                                    break
                        
                        # Preenche Saída
                        if s_val != "0":
                            for col_k in range(1, 12):
                                if master_df.at[target_idx, f'Saida{col_k}'] == "0":
                                    master_df.at[target_idx, f'Saida{col_k}'] = s_val
                                    break
                
                # Avança para a próxima expectativa de linha física
                current_physical_row += 1

        # Geração do nome do arquivo e salvamento
        final_filename = f"Ponto_IA_extraido_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        out_path = os.path.join(tempfile.gettempdir(), f"{job.id}.csv")
        master_df.to_csv(out_path, index=False, sep=';', encoding='utf-8-sig')
        
        job.meta.update({'status': 'completed', 'file_path': out_path, 'filename': final_filename})
        job.save()
        return out_path

    except Exception:
        if job: job.meta.update({'status': 'error', 'error': traceback.format_exc()}); job.save()
        return None
    finally:
        if os.path.exists(pdf_path):
            try: os.unlink(pdf_path)
            except: pass
