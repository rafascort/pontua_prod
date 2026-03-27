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

MAX_DOCAI_WORKERS = int(os.getenv('DOCAI_MAX_WORKERS', '60'))

# ─── LOG DE DIAGNÓSTICO ───────────────────────────────────────────────────────
def DIAG(msg):
    ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    print(f"[DIAG {ts}] {msg}", flush=True)
# ─────────────────────────────────────────────────────────────────────────────


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
        try:
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
        self.update_progress(1, 4, "Preparando páginas para envio...")

        reader = PdfReader(pdf_path)
        total  = len(valid_pages)

        page_pdfs = []
        for order, p in enumerate(valid_pages):
            writer = PdfWriter()
            writer.add_page(reader.pages[p['page_index']])
            buf = BytesIO()
            writer.write(buf)
            page_pdfs.append((order, buf.getvalue()))

        self.update_progress(1, 4, f"Enviando {total} página(s) para o Google em paralelo...")

        results = {}
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
                    1 + int(completed / total * 2),
                    4,
                    f"Google processou {completed}/{total} página(s)..."
                )

        self.update_progress(3, 4, "Consolidando resultados...")

        all_entities = []
        for order in sorted(results.keys()):
            entities, _ = results[order]
            all_entities.extend(entities)

        DIAG(f"Entidades brutas retornadas pelo DocAI: {len(all_entities)}")
        DIAG(f"Tipos distintos: {set(e.type_ for e in all_entities)}")
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


def extract_full_date(raw):
    """
    Retorna DD/MM/YYYY se o campo contém uma data completa.
    Ex: '05/07/2022' → '05/07/2022' | '5/7/2022' → '05/07/2022'
    Retorna None se não for data completa.
    """
    raw = str(raw or '').strip()
    match = re.match(r'^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$', raw)
    if match:
        d, m, y = match.groups()
        return f"{d.zfill(2)}/{m.zfill(2)}/{y}"
    return None


def extract_day_number(raw):
    """
    Fallback: extrai apenas o número do dia (01-31).
    Só usado quando o DocAI não retorna a data completa.
    Ex: '15' → '15' | '03/05' → '03'
    """
    raw = str(raw or '').strip()
    if not raw:
        return None
    if '/' in raw:
        raw = raw.split('/')[0].strip()
    d = re.sub(r'[^\d]', '', raw)
    if not d:
        return None
    n = int(d)
    return f"{n:02d}" if 1 <= n <= 31 else None


def _ocr_page(image):
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

        # ── LOG: input recebido ───────────────────────────────────────────────
        DIAG("=" * 70)
        DIAG(f"INÍCIO process_pdf_task | user={user_id} | pdf={pdf_path}")
        DIAG(f"Número de entradas em pages_json: {len(valid_pages)}")
        for i, p in enumerate(valid_pages):
            DIAG(f"  Entrada[{i}] → page_number={p.get('page_number')} | "
                 f"page_index={p.get('page_index')} | period={p.get('period')}")
        DIAG("=" * 70)

        # ── 1. Validação e ordenação cronológica ──────────────────────────────
        pages_validas = []
        for p in valid_pages:
            try:
                start_dt = datetime.strptime(p['period']['start_date'], '%d/%m/%Y')
                end_dt   = datetime.strptime(p['period']['end_date'],   '%d/%m/%Y')
                if end_dt < start_dt:
                    DIAG(f"  *** IGNORANDO página {p.get('page_number')}: "
                         f"end_date ({p['period']['end_date']}) < start_date "
                         f"({p['period']['start_date']}). Verifique o ano digitado.")
                    continue
                p['start_dt'] = start_dt
                p['end_dt']   = end_dt
                pages_validas.append(p)
            except ValueError as ve:
                DIAG(f"  *** IGNORANDO página {p.get('page_number')}: "
                     f"data inválida → {ve}")

        if not pages_validas:
            raise ValueError("Nenhuma página com período válido após validação.")

        pages_validas = sorted(pages_validas, key=lambda p: p['start_dt'])
        global_start  = min(p['start_dt'] for p in pages_validas)
        global_end    = max(p['end_dt']   for p in pages_validas)

        DIAG(f"Páginas válidas: {len(pages_validas)} / {len(valid_pages)}")
        DIAG(f"Período global: {global_start.date()} → {global_end.date()}")

        # ── 2. Tamanho do calendário por página (para chunking) ───────────────
        page_day_dicts = []
        page_sizes     = []
        for p in pages_validas:
            dr   = pd.date_range(start=p['start_dt'], end=p['end_dt'], freq='D')
            size = len(dr)
            page_sizes.append(size)
            # dict de fallback: só consulta se a data completa não estiver disponível
            day_dict = {f"{d.day:02d}": d.strftime('%d/%m/%Y') for d in dr}
            page_day_dicts.append(day_dict)
            DIAG(f"  Página {p['page_number']} → "
                 f"{p['start_dt'].date()} a {p['end_dt'].date()} | "
                 f"{size} dias de calendário")

        DIAG(f"page_sizes: {page_sizes} | soma: {sum(page_sizes)}")

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
        DIAG(f"Master calendar: {len(master_df)} dias | "
             f"{master_df['Dia'].iloc[0]} → {master_df['Dia'].iloc[-1]}")

        # ── 4. Document AI paralelo ───────────────────────────────────────────
        entities = extractor.process_pdf_parallel(pdf_path, pages_validas)
        extractor.update_progress(4, 4, "Finalizando planilha...")

        rows_all = [
            e for e in entities
            if e.type_.lower().replace(' ', '_').replace('-', '_') == 'tabela_marcacoes'
        ]
        DIAG(f"Total entidades 'tabela_marcacoes': {len(rows_all)}")

        # ── 5. Distribuição por página e preenchimento ────────────────────────
        # Estratégia: ignora o chunking para resolução de datas.
        # Processa TODAS as entidades de uma vez usando a data completa
        # retornada pelo DocAI. O chunking só serve para controlar o
        # range de fallback quando a data completa não está disponível.
        DIAG("Processando todas as entidades com data completa (sem chunking)...")

        filled_count      = 0
        skip_no_date      = 0
        skip_no_row       = 0
        skip_duplicado    = 0
        full_date_hits    = 0
        fallback_day_hits = 0

        # Monta um dicionário global de fallback: dia → lista de datas possíveis
        # ordenadas cronologicamente. Usado apenas quando o DocAI não retorna
        # a data completa (raro com o processor atual).
        global_day_to_dates: dict[str, list[str]] = {}
        for p, day_dict in zip(pages_validas, page_day_dicts):
            for day_num, full_dt in day_dict.items():
                global_day_to_dates.setdefault(day_num, []).append(full_dt)

        for entity in rows_all:
            shard_text = getattr(entity, '_shard_text', '')
            data = {
                prop.type_.lower(): get_text_safely(prop, shard_text)
                for prop in entity.properties
            }

            raw_dia = data.get('dia', data.get('data', ''))

            # ── RESOLUÇÃO DE DATA ─────────────────────────────────────────────
            target_date = None

            # 1) Data completa retornada pelo DocAI (caminho ideal, sem colisão)
            full_date = extract_full_date(raw_dia)
            if full_date and full_date in date_to_row:
                target_date = full_date
                full_date_hits += 1
            else:
                # 2) Fallback: só o número do dia foi retornado.
                #    Usa a primeira data possível ainda não preenchida.
                day = extract_day_number(raw_dia)
                if day and day in global_day_to_dates:
                    for candidate in global_day_to_dates[day]:
                        if candidate in date_to_row:
                            idx_cand = date_to_row[candidate]
                            if master_df.at[idx_cand, 'Entrada1'] == "0":
                                target_date = candidate
                                fallback_day_hits += 1
                                break
            # ─────────────────────────────────────────────────────────────────

            if target_date is None:
                skip_no_date += 1
                continue

            target_idx = date_to_row.get(target_date)
            if target_idx is None:
                skip_no_row += 1
                continue

            # ── CORREÇÃO DE DUPLICAÇÃO ────────────────────────────────────────
            # O relatório PontoMais pode repetir a mesma linha na virada de
            # página física. Se a data já foi preenchida, ignoramos o duplicado.
            if master_df.at[target_idx, 'Entrada1'] != "0":
                skip_duplicado += 1
                DIAG(f"  SKIP duplicado: '{target_date}' já preenchida. "
                     f"Ignorando entity com data='{raw_dia}'.")
                continue
            # ─────────────────────────────────────────────────────────────────

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

        # ── Resumo final ──────────────────────────────────────────────────────
        dias_preenchidos = (master_df['Entrada1'] != "0").sum()
        DIAG(f"Linhas preenchidas: {filled_count} | "
             f"Data completa: {full_date_hits} | "
             f"Fallback dia: {fallback_day_hits} | "
             f"Duplicados ignorados: {skip_duplicado} | "
             f"Skip sem data: {skip_no_date} | "
             f"Skip fora do range: {skip_no_row}")
        DIAG(f"Dias com Entrada1 != '0': {dias_preenchidos} / {len(master_df)}")

        # ── 6. Salvar CSV ─────────────────────────────────────────────────────
        random_id      = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        final_filename = f"Ponto_Extraido_{random_id}.csv"
        out_path       = os.path.join(tempfile.gettempdir(), f"{job.id}.csv")
        master_df.to_csv(out_path, index=False, sep=';', encoding='utf-8-sig')

        DIAG(f"CSV salvo: {out_path} | filename: {final_filename}")
        DIAG("=" * 70)

        job.meta.update({'status': 'completed', 'file_path': out_path, 'filename': final_filename})
        job.save()
        return out_path

    except Exception:
        err = traceback.format_exc()
        print(f"[ERRO] {err}")
        job.meta.update({'status': 'error', 'error': err})
        job.save()
        return None
