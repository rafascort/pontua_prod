# /opt/pontua/AutoPonto/backend_api/extractor_geral_ai.py

import os
import tempfile
import pandas as pd
import logging
import re
import traceback
import platform
import time
import random
import string
from io import BytesIO
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from rq import get_current_job
from google.cloud import documentai_v1 as documentai
from google.cloud import storage
from pypdf import PdfReader, PdfWriter
from pdf2image import convert_from_path
import pytesseract

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ExtractorAI")

if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# ─────────────────────────────────────────────────────────────────────────────
# Nº de requisições paralelas ao Document AI.
# Threads são 100% I/O-bound (só esperam resposta de rede do Google).
# Não consomem CPU — podem ser muitas sem impacto no servidor.
# 30 garante que até 30 páginas processem em 1 único turno (~5-10s).
# Para processos maiores (ex: 50 páginas), ainda serão 2 turnos de 25.
# Pode ser ajustado via env: DOCAI_MAX_WORKERS=50
# ─────────────────────────────────────────────────────────────────────────────
MAX_DOCAI_WORKERS = int(os.getenv('DOCAI_MAX_WORKERS', '60'))


class ExtractorGeralAI:
    def __init__(self, model_type='6', job=None):
        self.model_type      = model_type
        self.job             = job
        self.project_id      = os.getenv('GOOGLE_CLOUD_PROJECT')
        self.location        = os.getenv('DOCAI_PROCESSOR_LOCATION')
        self.processor_id    = os.getenv('DOCAI_PROCESSOR_ID')
        self.gcs_bucket_name = os.getenv('GCS_BUCKET_NAME')
        self.client = documentai.DocumentProcessorServiceClient(
            client_options={"api_endpoint": f"{self.location}-documentai.googleapis.com"}
        )
        self.storage_client = storage.Client()
        self._processor_name = self.client.processor_path(
            self.project_id, self.location, self.processor_id
        )

    def update_progress(self, current, total, message, status='processing', extra_info=None):
        if self.job:
            progress = int((current / total) * 100) if total > 0 else 0
            meta = {
                'progress': progress, 'message': message,
                'current_step': current, 'total_steps': total,
                'status': status, 'timestamp': datetime.now().isoformat()
            }
            if extra_info:
                meta.update(extra_info)
            self.job.meta.update(meta)
            self.job.save_meta()

    def _process_single_page(self, pdf_bytes_single: bytes, page_order: int):
        """
        Envia UMA página para o Document AI síncrono (online processing).
        Retorna (page_order, entities, text) ou (page_order, [], "").

        IMPORTANTE: cria um cliente gRPC próprio por chamada.
        O cliente compartilhado (self.client) serializa requisições no mesmo
        canal gRPC — com ele, 14 threads viram 14 chamadas em fila (~48s).
        Com cliente por thread, cada uma tem canal independente (~5-8s total).
        """
        try:
            # Cliente independente por thread → canal gRPC exclusivo → sem serialização
            thread_client = documentai.DocumentProcessorServiceClient(
                client_options={"api_endpoint": f"{self.location}-documentai.googleapis.com"}
            )
            request = documentai.ProcessRequest(
                name=self._processor_name,
                raw_document=documentai.RawDocument(
                    content=pdf_bytes_single,
                    mime_type="application/pdf"
                )
            )
            result   = thread_client.process_document(request=request)
            doc      = result.document
            doc_text = doc.text or ""
            for e in doc.entities:
                e._shard_text = doc_text
            return page_order, list(doc.entities), doc_text
        except Exception as ex:
            print(f"[ERRO] Página {page_order} falhou no Document AI: {ex}")
            return page_order, [], ""

    def process_pdf_parallel(self, pdf_path: str, valid_pages: list):
        """
        Processa cada página individualmente em paralelo via Document AI síncrono.
        As páginas são enviadas como PDFs de 1 página cada.
        Resultados são reordenados por page_order para manter sequência correta.
        """
        self.update_progress(1, 4, "Preparando páginas para envio...")

        reader = PdfReader(pdf_path)
        total  = len(valid_pages)

        # Gera PDF de 1 página para cada página selecionada
        page_pdfs = []   # lista de (page_order, pdf_bytes)
        for order, p in enumerate(valid_pages):
            writer = PdfWriter()
            writer.add_page(reader.pages[p['page_index']])
            buf = BytesIO()
            writer.write(buf)
            page_pdfs.append((order, buf.getvalue()))

        self.update_progress(1, 4,
            f"Enviando {total} página(s) para o Google em paralelo...")

        # ── Paralelo I/O-bound: seguro, não consome CPU ───────────────────────
        results = {}   # {page_order: (entities, text)}

        with ThreadPoolExecutor(max_workers=min(MAX_DOCAI_WORKERS, total)) as executor:
            futures = {
                executor.submit(self._process_single_page, pdf_bytes, order): order
                for order, pdf_bytes in page_pdfs
            }

            completed = 0
            for future in as_completed(futures):
                order, entities, text = future.result()
                results[order] = (entities, text)
                completed += 1
                self.update_progress(
                    1 + int(completed / total * 2),   # progresso de 1→3
                    4,
                    f"Google processou {completed}/{total} página(s)..."
                )

        self.update_progress(3, 4, "Consolidando resultados...")

        # ── Reordena por page_order para manter sequência correta ─────────────
        all_entities = []
        for order in sorted(results.keys()):
            entities, _ = results[order]
            all_entities.extend(entities)

        print(f"[DIAG] Entidades brutas: {len(all_entities)} | tipos: {set(e.type_ for e in all_entities)}")
        return all_entities


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_text_safely(prop, shard_text=""):
    if prop.mention_text:
        return prop.mention_text.strip()
    if prop.text_anchor and prop.text_anchor.text_segments and shard_text:
        extracted = ""
        for seg in prop.text_anchor.text_segments:
            extracted += shard_text[int(seg.start_index or 0):int(seg.end_index or 0)]
        return extracted.strip() or "0"
    return "0"


def normalize_time(val):
    if not val or val == '0' or str(val).lower() == 'nan':
        return "0"
    d = re.sub(r'[^\d]', '', str(val))
    if len(d) >= 4: return f"{d[:2]}:{d[2:4]}"
    if len(d) == 3: return f"0{d[0]}:{d[1:3]}"
    return "0"


def extract_day_number(raw):
    d = re.sub(r'[^\d]', '', str(raw or ''))
    if not d:
        return None
    n = int(d)
    return f"{n:02d}" if 1 <= n <= 31 else None


def _ocr_page(image):
    """OCR no topo da imagem para extrair período."""
    try:
        top   = image.crop((0, 0, image.size[0], int(image.size[1] * 0.3)))
        text  = pytesseract.image_to_string(top, lang='por')
        dates = re.findall(r'\b(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\b', text)
        if len(dates) >= 2:
            return {
                'start_date': dates[0].replace('.', '/'),
                'end_date':   dates[1].replace('.', '/')
            }
        return None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Tarefas RQ
# ─────────────────────────────────────────────────────────────────────────────

def extract_periods_task(pdf_path, pages, user_id):
    """
    OCR otimizado:
    - convert_from_path em batch (1 chamada pdftoppm para todas as páginas)
    - DPI 200 (suficiente para datas de cabeçalho)
    - OCR sequencial (tesseract = CPU-bound, não paralelizar)
    """
    job = get_current_job()
    if not job:
        return None
    job.meta['user_id'] = user_id
    job.save_meta()
    extractor = ExtractorGeralAI(job=job)

    try:
        reader    = PdfReader(pdf_path)
        total_pdf = len(reader.pages)
        indices_set = set()

        if pages:
            for part in str(pages).split(','):
                part = part.strip()
                if '-' in part:
                    s, e = map(int, part.split('-'))
                    indices_set.update(range(s - 1, min(e, total_pdf)))
                elif part.isdigit():
                    idx = int(part) - 1
                    if 0 <= idx < total_pdf:
                        indices_set.add(idx)
            indices = sorted(list(indices_set))
        else:
            indices = list(range(total_pdf))

        total_selected = len(indices)
        extractor.update_progress(0, total_selected, "Convertendo páginas...")

        # Batch convert: 1 chamada pdftoppm para o range inteiro
        min_page = min(indices) + 1
        max_page = max(indices) + 1
        all_images = convert_from_path(pdf_path, dpi=200,
                                       first_page=min_page, last_page=max_page)

        relative_to_absolute = {
            (min_page - 1 + i): all_images[i]
            for i in range(len(all_images))
        }

        res = []
        for count, page_idx in enumerate(indices, 1):
            extractor.update_progress(
                count, total_selected,
                f"Lendo cabeçalho {count}/{total_selected} (Pág {page_idx + 1})..."
            )
            image  = relative_to_absolute.get(page_idx)
            period = _ocr_page(image) if image is not None else None
            res.append({
                'page_number': page_idx + 1,
                'page_index':  page_idx,
                'period':      period
            })

        job.meta.update({'status': 'completed', 'result': res, 'pdf_path': pdf_path})
        job.save()
        return res

    except Exception:
        err = traceback.format_exc()
        print(f"[ERRO][extract_periods_task] {err}")
        job.meta.update({'status': 'error', 'error': err})
        job.save()
        return None


def process_pdf_task(pdf_path, pages_json, model_type, user_id):
    job = get_current_job()
    if not job:
        return None
    job.meta['user_id'] = user_id
    job.save_meta()
    extractor  = ExtractorGeralAI(model_type, job)
    day_map_pt = {0:"seg",1:"ter",2:"qua",3:"qui",4:"sex",5:"sab",6:"dom"}

    try:
        valid_pages = pages_json

        # ── 1. Ordenação cronológica ──────────────────────────────────────────
        for p in valid_pages:
            p['start_dt'] = datetime.strptime(p['period']['start_date'], '%d/%m/%Y')
            p['end_dt']   = datetime.strptime(p['period']['end_date'],   '%d/%m/%Y')

        valid_pages  = sorted(valid_pages, key=lambda p: p['start_dt'])
        global_start = min(p['start_dt'] for p in valid_pages)
        global_end   = max(p['end_dt']   for p in valid_pages)

        # ── 2. Lookup dia→data por página ─────────────────────────────────────
        page_day_dicts = []
        page_sizes     = []
        for p in valid_pages:
            dr = pd.date_range(start=p['start_dt'], end=p['end_dt'], freq='D')
            page_sizes.append(len(dr))
            page_day_dicts.append({f"{d.day:02d}": d.strftime('%d/%m/%Y') for d in dr})

        # ── 3. Calendário mestre ──────────────────────────────────────────────
        full_range = pd.date_range(start=global_start, end=global_end, freq='D')
        master_df  = pd.DataFrame({
            'Dia':      full_range.strftime('%d/%m/%Y'),
            'Dia_Sema': full_range.weekday.map(day_map_pt)
        })
        for i in range(1, 12):
            master_df[f'Entrada{i}'] = "0"
            master_df[f'Saida{i}']   = "0"

        date_to_row = {row['Dia']: idx for idx, row in master_df.iterrows()}

        # ── 4. Document AI paralelo (I/O-bound, seguro) ───────────────────────
        entities = extractor.process_pdf_parallel(pdf_path, valid_pages)
        extractor.update_progress(4, 4, "Finalizando planilha...")

        rows_all = [
            e for e in entities
            if e.type_.lower().replace(' ', '_').replace('-', '_') == 'tabela_marcacoes'
        ]

        # ── 5. Blocos por página com lookup dia→data ──────────────────────────
        entity_ptr   = 0
        filled_count = 0

        for page_size, day_to_date in zip(page_sizes, page_day_dicts):
            chunk = rows_all[entity_ptr:entity_ptr + page_size]
            entity_ptr += page_size

            for entity in chunk:
                shard_text = getattr(entity, '_shard_text', '')
                data = {
                    prop.type_.lower(): get_text_safely(prop, shard_text)
                    for prop in entity.properties
                }

                day = extract_day_number(data.get('dia', data.get('data', '')))
                if not day or day not in day_to_date:
                    continue

                target_idx = date_to_row.get(day_to_date[day])
                if target_idx is None:
                    continue

                for k in range(1, 12):
                    e_val = normalize_time(data.get(f'entrada{k}', data.get(f'entrada_{k}', "0")))
                    s_val = normalize_time(data.get(f'saida{k}',   data.get(f'saída{k}',   "0")))
                    if e_val != "0":
                        for c in range(1, 12):
                            if master_df.at[target_idx, f'Entrada{c}'] == "0":
                                master_df.at[target_idx, f'Entrada{c}'] = e_val
                                break
                    if s_val != "0":
                        for c in range(1, 12):
                            if master_df.at[target_idx, f'Saida{c}'] == "0":
                                master_df.at[target_idx, f'Saida{c}'] = s_val
                                break

                filled_count += 1

        # ── 6. Salvar CSV ─────────────────────────────────────────────────────
        random_id      = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        final_filename = f"Ponto_Extraido_{random_id}.csv"
        out_path       = os.path.join(tempfile.gettempdir(), f"{job.id}.csv")
        master_df.to_csv(out_path, index=False, sep=';', encoding='utf-8-sig')

        job.meta.update({'status': 'completed', 'file_path': out_path, 'filename': final_filename})
        job.save()
        return out_path

    except Exception:
        err = traceback.format_exc()
        print(f"[ERRO] {err}")
        job.meta.update({'status': 'error', 'error': err})
        job.save()
        return None
