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

    def process_pdf_batch(self, pdf_path, valid_pages):
        self.update_progress(1, 4, "Preparando arquivo para processamento em lote...")

        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        for p in valid_pages:
            writer.add_page(reader.pages[p['page_index']])

        pdf_bytes = BytesIO()
        writer.write(pdf_bytes)
        pdf_bytes.seek(0)

        bucket     = self.storage_client.bucket(self.gcs_bucket_name)
        input_blob = f"input/{self.job.id}_batch.pdf"
        bucket.blob(input_blob).upload_from_file(pdf_bytes, content_type="application/pdf")

        gcs_in  = f"gs://{self.gcs_bucket_name}/{input_blob}"
        gcs_out = f"gs://{self.gcs_bucket_name}/output/{self.job.id}/"

        request = documentai.BatchProcessRequest(
            name=self.client.processor_path(self.project_id, self.location, self.processor_id),
            input_documents=documentai.BatchDocumentsInputConfig(
                gcs_documents=documentai.GcsDocuments(documents=[
                    documentai.GcsDocument(gcs_uri=gcs_in, mime_type="application/pdf")
                ])
            ),
            document_output_config=documentai.DocumentOutputConfig(
                gcs_output_config={"gcs_uri": gcs_out}
            ),
        )

        operation  = self.client.batch_process_documents(request)
        start_time = time.time()
        while not operation.done():
            elapsed = int(time.time() - start_time)
            self.update_progress(2, 4, f"Google processando... ({elapsed}s)",
                                 extra_info={'batch_timer': elapsed})
            time.sleep(2)
        operation.result(timeout=600)

        self.update_progress(3, 4, "Lendo resultados da extração...")
        blobs = sorted(list(bucket.list_blobs(prefix=f"output/{self.job.id}/")),
                       key=lambda x: x.name)

        all_entities = []
        for b in blobs:
            if b.name.endswith(".json"):
                shard      = documentai.Document.from_json(
                    b.download_as_bytes(), ignore_unknown_fields=True)
                shard_text = shard.text or ""
                for e in shard.entities:
                    e._shard_text = shard_text
                all_entities.extend(shard.entities)

        for b in blobs:
            b.delete()
        bucket.blob(input_blob).delete()

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
    """Roda tesseract na faixa superior da imagem. Retorna period dict ou None."""
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
    OTIMIZAÇÃO APLICADA:
    - convert_from_path em BATCH: uma única chamada pdftoppm para todas as
      páginas do range. Elimina N-1 inicializações de processo e a leitura
      repetida do PDF do disco.
    - DPI 200: datas de cabeçalho são texto grande, não precisa de 300 DPI.
      Reduz memória e tempo de conversão em ~55%.
    - OCR permanece SEQUENCIAL: tesseract já ocupa bem 1 CPU por chamada.
      Paralelismo causaria N processos simultâneos e travaria o servidor.
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

        # ── Batch convert: UMA chamada pdftoppm para o range inteiro ──────────
        # Antes: N chamadas (1 por página) → N inicializações de pdftoppm
        # Agora: 1 chamada cobrindo min→max → todas as imagens retornadas juntas
        #
        min_page = min(indices) + 1   # 1-based
        max_page = max(indices) + 1

        all_images = convert_from_path(
            pdf_path,
            dpi=200,
            first_page=min_page,
            last_page=max_page,
        )

        # Mapeia posição relativa → page_idx absoluto
        # all_images[0] = página min_page-1, all_images[1] = min_page, etc.
        relative_to_absolute = {
            (min_page - 1 + i): all_images[i]
            for i in range(len(all_images))
        }

        # ── OCR sequencial em cada página selecionada ─────────────────────────
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
            day_to_date = {f"{d.day:02d}": d.strftime('%d/%m/%Y') for d in dr}
            page_day_dicts.append(day_to_date)

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

        # ── 4. Processamento no Document AI ──────────────────────────────────
        entities = extractor.process_pdf_batch(pdf_path, valid_pages)
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
