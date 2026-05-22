# /opt/pontua/AutoPonto/backend_api/extractor_geral_ai.py

import os
import json
import tempfile
import pandas as pd
import logging
import re
import traceback
import time
import random
import string
from io import BytesIO
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import redis as redis_lib
from rq import get_current_job
from google.cloud import documentai_v1 as documentai
from google.cloud import storage
from google import genai
from pypdf import PdfReader, PdfWriter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ExtractorAI")

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google_genai.models").setLevel(logging.WARNING)
os.environ.setdefault('GRPC_VERBOSITY', 'ERROR')
os.environ.setdefault('GRPC_TRACE', '')

MAX_DOCAI_WORKERS  = 120
MAX_GEMINI_WORKERS = 20
DOCAI_RPM_LIMIT    = 220
DOCAI_RATE_KEY     = 'docai_sliding_window'
_redis = redis_lib.Redis(host='localhost', port=6379, db=0)

_gemini = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
GEMINI_MODEL = 'gemini-2.5-flash'


# ─── LOG CENTRAL ─────────────────────────────────────────────────────────────
def LOG(label, value, level='INFO'):
    ts     = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    prefix = {'INFO': '[LOG ]', 'WARN': '[WARN]', 'ERR ': '[ERR ]'}.get(level, '[LOG ]')
    print(f"{prefix} {ts}  {label:<30} {value}", flush=True)

def LOG_SEP(title=''):
    line = '─' * 70
    if title:
        pad  = max(0, (70 - len(title) - 2) // 2)
        line = '─' * pad + f' {title} ' + '─' * pad
    print(f"[LOG ] {line}", flush=True)


# ─── RATE LIMITER GLOBAL ─────────────────────────────────────────────────────
def _get_rpm_usage():
    now = time.time()
    try:
        return int(_redis.zcount(DOCAI_RATE_KEY, now - 60.0, '+inf'))
    except Exception:
        return 0


def _acquire_docai_slot(job_id='?', page_order=0, timeout=300):
    start      = time.time()
    waited     = 0.0
    first_wait = True

    while True:
        now          = time.time()
        window_start = now - 60.0

        pipe = _redis.pipeline()
        pipe.zremrangebyscore(DOCAI_RATE_KEY, 0, window_start)
        pipe.zcard(DOCAI_RATE_KEY)
        _, current_count = pipe.execute()
        current_count = int(current_count)

        if current_count < DOCAI_RPM_LIMIT:
            member = f"{now:.6f}:{job_id}:{page_order}:{random.random()}"
            _redis.zadd(DOCAI_RATE_KEY, {member: now})
            _redis.expire(DOCAI_RATE_KEY, 120)
            return current_count + 1, round(waited, 1)

        if time.time() - start > timeout:
            raise TimeoutError(
                f"Timeout de {timeout}s aguardando slot DocAI "
                f"(uso atual: {current_count}/{DOCAI_RPM_LIMIT})"
            )

        if first_wait:
            first_wait = False
            oldest = _redis.zrange(DOCAI_RATE_KEY, 0, 0, withscores=True)
            secs_to_free = max(0.5, (oldest[0][1] + 60.0) - time.time()) if oldest else 1.0
            LOG(f"  rate limit pág {page_order}",
                f"uso={current_count}/{DOCAI_RPM_LIMIT} — "
                f"aguardando ~{round(secs_to_free, 1)}s para slot liberar  "
                f"(job {job_id[:8]}...)", 'WARN')

        time.sleep(0.5)
        waited += 0.5


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

    def spatial_sort_entities(self, entities):
        rows = [e for e in entities
                if e.type_.lower() == 'tabela_marcacoes']

        def get_y(e):
            try:
                return e.page_anchor.page_refs[0].bounding_poly.normalized_vertices[0].y
            except Exception:
                return 0.0

        return sorted(rows, key=get_y)

    def _process_single_page(self, pdf_bytes_single: bytes, page_order: int, job_id: str):
        slot_num, waited = _acquire_docai_slot(job_id=job_id, page_order=page_order)
        if waited > 0:
            LOG(f"  pág {page_order} aguardou",
                f"{waited}s por slot  (uso ao enviar: {slot_num}/{DOCAI_RPM_LIMIT})", 'WARN')
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
            sorted_ents = self.spatial_sort_entities(doc.entities)
            return page_order, sorted_ents, doc_text, slot_num, waited
        except Exception as ex:
            print(f"[ERR ] Página {page_order} falhou no Document AI: {ex}", flush=True)
            return page_order, [], "", slot_num, waited

    def process_pdf_parallel(self, pdf_path: str, valid_pages: list, job_id: str):
        """Dedupliça pelo page_index (cada página única é processada UMA vez no DocAI)."""
        self.update_progress(1, 4, "Preparando páginas para envio...")
        reader = PdfReader(pdf_path)

        seen_indices = set()
        unique_pages = []
        for p in valid_pages:
            pidx = p['page_index']
            if pidx not in seen_indices:
                seen_indices.add(pidx)
                unique_pages.append(p)

        total = len(unique_pages)

        page_pdfs = []
        index_to_order = {}
        for order, p in enumerate(unique_pages):
            writer = PdfWriter()
            writer.add_page(reader.pages[p['page_index']])
            buf = BytesIO()
            writer.write(buf)
            page_pdfs.append((order, buf.getvalue()))
            index_to_order[p['page_index']] = order

        self.update_progress(1, 4, f"Enviando {total} página(s) para processamento...")

        results      = {}
        total_waited = 0.0

        with ThreadPoolExecutor(max_workers=min(MAX_DOCAI_WORKERS, total)) as executor:
            futures = {
                executor.submit(self._process_single_page, pdf_bytes, order, job_id): order
                for order, pdf_bytes in page_pdfs
            }
            completed = 0
            for future in as_completed(futures):
                order, entities, text, slot_num, waited = future.result()
                results[order] = (entities, text)
                total_waited  += waited
                completed     += 1
                self.update_progress(
                    1 + int(completed / total * 2), 4,
                    f"Processando {completed}/{total} página(s)..."
                )

        self.update_progress(3, 4, "Consolidando resultados...")
        return results, round(total_waited, 1), index_to_order


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


def _is_valid_time(hh: int, mm: int) -> bool:
    """Retorna True se HH e MM formam horário válido (00-23 e 00-59)."""
    return 0 <= hh <= 23 and 0 <= mm <= 59


def normalize_time(val):
    """
    Normaliza valor para formato HH:MM ou retorna "0" se não conseguir.

    Estratégias (em ordem de prioridade):
    1. String vazia/None/zero/nan → "0"
    2. Tem ":" no meio → tenta extrair "HH:MM" via regex
       - Se inválido, tenta tirar lixo e tentar de novo
    3. Sem ":", só dígitos:
       - 4 dígitos: HHMM direto
       - 3 dígitos: 0HMM
       - 5+ dígitos: tenta combinações:
         a) Tira o último dígito → testa HHMM válido
         b) Tira o primeiro dígito → testa HHMM válido
         c) Pega 4 do meio → testa HHMM válido
       - Se nenhuma combinação dá horário válido → "0"
    4. Valida no final: HH 0-23, MM 0-59. Se inválido → "0"
    """
    if not val or val == '0' or str(val).lower() == 'nan':
        return "0"

    s = str(val).strip()
    if not s:
        return "0"

    # Estratégia A: tem ":" — tenta achar "HH:MM" como subpadrão
    if ':' in s:
        # Extrai todos os candidatos "DD:DD" possíveis
        match = re.search(r'(\d{1,2}):(\d{1,2})', s)
        if match:
            hh = int(match.group(1))
            mm_str = match.group(2)
            # Pad MM se vier com 1 dígito
            if len(mm_str) == 1:
                mm = int(mm_str) * 10  # ex: ":4" vira ":40"? não — melhor ignorar
                return "0"
            mm = int(mm_str[:2])
            if _is_valid_time(hh, mm):
                return f"{hh:02d}:{mm:02d}"
            # OCR leu "0" como "3" na dezena da hora (ex: "36:25" → "06:25")
            # Se a hora tem 2 dígitos e é > 23, tenta só o segundo dígito
            if hh > 23 and len(match.group(1)) == 2:
                hh_alt = int(match.group(1)[1])
                if _is_valid_time(hh_alt, mm):
                    return f"{hh_alt:02d}:{mm:02d}"

        # Caso "#18\n:" — começa com algo + número + ":" sem MM legível

        # Caso "#18\n:" — começa com algo + número + ":" sem MM legível
        # Tenta ainda extrair só os dígitos
        digits_only = re.sub(r'[^\d]', '', s)
        if len(digits_only) == 4:
            hh, mm = int(digits_only[:2]), int(digits_only[2:])
            if _is_valid_time(hh, mm):
                return f"{hh:02d}:{mm:02d}"
        elif len(digits_only) >= 5:
            # Tira o excesso do final ou do início (mesma lógica da Estratégia B)
            for cand in [digits_only[:4], digits_only[1:5]]:
                hh, mm = int(cand[:2]), int(cand[2:])
                if _is_valid_time(hh, mm):
                    return f"{hh:02d}:{mm:02d}"
        return "0"

    # Estratégia B: sem ":", só dígitos extraídos
    digits = re.sub(r'[^\d]', '', s)
    if not digits:
        return "0"

    # 4 dígitos: HHMM direto
    if len(digits) == 4:
        hh, mm = int(digits[:2]), int(digits[2:])
        if _is_valid_time(hh, mm):
            return f"{hh:02d}:{mm:02d}"
        return "0"

    # 3 dígitos: 0HMM
    if len(digits) == 3:
        hh, mm = int(digits[0]), int(digits[1:])
        if _is_valid_time(hh, mm):
            return f"{hh:02d}:{mm:02d}"
        return "0"

    # 5+ dígitos: tenta combinações
    if len(digits) >= 5:
        candidates = []

        # Tira o último (lixo no final)
        c1 = digits[:4]
        candidates.append(('trunca final', c1))

        # Tira o primeiro (lixo no início)
        c2 = digits[1:5]
        candidates.append(('trunca início', c2))

        # Se 6 dígitos, tenta meio
        if len(digits) == 6:
            c3 = digits[1:5]
            candidates.append(('meio', c3))

        for nome, cand in candidates:
            if len(cand) == 4:
                hh, mm = int(cand[:2]), int(cand[2:])
                if _is_valid_time(hh, mm):
                    return f"{hh:02d}:{mm:02d}"

        return "0"

    # 1 ou 2 dígitos: não dá pra montar HH:MM
    return "0"


def normalize_date(date_str, default_year):
    if not date_str:
        return None
    date_str = re.sub(r'[^\d/.-]', '', str(date_str)).replace('.', '/').replace('-', '/')
    parts = date_str.split('/')
    if len(parts) >= 2:
        day   = parts[0].zfill(2)
        month = parts[1].zfill(2)
        year  = parts[2] if len(parts) == 3 else str(default_year)
        if len(str(year)) == 2:
            year = f"20{year}"
        try:
            datetime.strptime(f"{day}/{month}/{year}", '%d/%m/%Y')
            return f"{day}/{month}/{year}"
        except ValueError:
            return None
    return None


def extract_full_date(raw):
    raw = str(raw or '').strip()
    match = re.match(r'^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$', raw)
    if match:
        d, m, y = match.groups()
        try:
            datetime.strptime(f"{d.zfill(2)}/{m.zfill(2)}/{y}", '%d/%m/%Y')
            return f"{d.zfill(2)}/{m.zfill(2)}/{y}"
        except ValueError:
            return None
    return None


def infer_date_by_position(data_ia, expected_date, default_year):
    if not data_ia:
        return expected_date

    normalized = normalize_date(data_ia, default_year)

    if normalized == expected_date:
        return normalized

    if normalized:
        ai_day  = normalized.split('/')[0].lstrip('0') or '0'
        exp_day = expected_date.split('/')[0].lstrip('0') or '0'

        if len(ai_day) == 1 and exp_day.endswith(ai_day):
            ai_rest  = normalized[2:]
            exp_rest = expected_date[2:]
            if ai_rest.startswith(exp_rest[:3]):
                return expected_date

        if len(normalized) == 10:
            return normalized

    return expected_date


def _fill_slots(master_df, target_idx, data):
    preencheu = False
    for k in range(1, 12):
        e_val = normalize_time(data.get(f'entrada{k}', data.get(f'entrada_{k}', "0")))
        s_val = normalize_time(data.get(f'saida{k}',   data.get(f'saída{k}',   "0")))

        if e_val == "0" and s_val == "0":
            continue

        if s_val != "0":
            for c in range(1, 12):
                if master_df.at[target_idx, f'Saida{c}'] == "0":
                    master_df.at[target_idx, f'Saida{c}'] = s_val
                    preencheu = True
                    break

        if e_val != "0":
            colocado_como_saida = False
            for c in range(1, 12):
                entrada_c = master_df.at[target_idx, f'Entrada{c}']
                saida_c   = master_df.at[target_idx, f'Saida{c}']
                if entrada_c != "0" and saida_c == "0" and e_val > entrada_c:
                    master_df.at[target_idx, f'Saida{c}'] = e_val
                    preencheu = True
                    colocado_como_saida = True
                    break

            if not colocado_como_saida:
                for c in range(1, 12):
                    if master_df.at[target_idx, f'Entrada{c}'] == "0":
                        master_df.at[target_idx, f'Entrada{c}'] = e_val
                        preencheu = True
                        break

    return preencheu


def _has_empty_slots(master_df, target_idx):
    for c in range(1, 12):
        if master_df.at[target_idx, f'Entrada{c}'] == "0":
            return True
        if master_df.at[target_idx, f'Saida{c}'] == "0":
            return True
    return False


def _is_duplicate_values(master_df, target_idx, data):
    existing_entradas = {
        master_df.at[target_idx, f'Entrada{c}']
        for c in range(1, 12)
        if master_df.at[target_idx, f'Entrada{c}'] != "0"
    }
    existing_saidas = {
        master_df.at[target_idx, f'Saida{c}']
        for c in range(1, 12)
        if master_df.at[target_idx, f'Saida{c}'] != "0"
    }
    existing_all = existing_entradas | existing_saidas

    has_new_value = False
    for k in range(1, 12):
        e_val = normalize_time(data.get(f'entrada{k}', data.get(f'entrada_{k}', "0")))
        s_val = normalize_time(data.get(f'saida{k}',   data.get(f'saída{k}',   "0")))
        if e_val != "0" and e_val not in existing_all:
            has_new_value = True
            break
        if s_val != "0" and s_val not in existing_all:
            has_new_value = True
            break

    return not has_new_value


# ─────────────────────────────────────────────────────────────────────────────
# Filtro de entidades por região
# ─────────────────────────────────────────────────────────────────────────────

def _parse_day_number(raw_str):
    """
    Extrai número do dia (1-31) de uma string bruta do DocAI,
    tolerando o artefato OCR onde um "1" adjacente é lido junto
    com o número do dia (ex: "102" para dia 2, "120" para dia 20).

    Regra de correção (segura):
      Se o número extraído > 31, tenta os últimos 2 dígitos.
      Códigos de jornada (684, 795, 796…) têm últimos 2 dígitos
      acima de 31 e continuam sendo rejeitados corretamente.

    Retorna int entre 1 e 31, ou None se não for possível extrair
    um dia válido. Nunca lança exceção.
    """
    if not raw_str:
        return None
    raw_clean = re.sub(r'[^\d]', '', str(raw_str).split('/')[0])
    if not raw_clean:
        return None
    try:
        n = int(raw_clean)
    except (ValueError, OverflowError):
        return None

    # Caso normal: já é um dia válido
    if 1 <= n <= 31:
        return n

    # Artefato OCR: "1" prefixado — tenta últimos 2 dígitos
    # Exemplo: "102" → 02 = 2 ✓  |  "120" → 20 ✓  |  "684" → 84 > 31 ✗
    if n > 31 and len(raw_clean) >= 3:
        tail = int(raw_clean[-2:])
        if 1 <= tail <= 31:
            return tail

    return None


def _entity_falls_in_period(entity, period_start, period_end, default_year):
    """
    Decide se uma entidade do DocAI pertence ao período da região.

    Estratégia: usa o campo 'data' (dia) extraído pelo DocAI.
    Se a data extraída cabe no intervalo [period_start, period_end], pertence.

    Funciona porque o DocAI extrai o número do dia (1-31) em cada linha,
    e cada região tem um período conhecido (definido pelo usuário ou Gemini).

    Como funciona com bbox indisponível: este é o mecanismo PRINCIPAL.
    """
    raw_data = ''
    for prop in entity.properties:
        if prop.type_.lower() in ('data', 'dia'):
            shard_text = getattr(entity, '_shard_text', '')
            raw_data = get_text_safely(prop, shard_text)
            break

    if not raw_data:
        return None  # sem data → não dá pra decidir

    # Extrai o número do dia usando helper que trata artefato OCR '1XX'
    # Ex: '102' → 2, '120' → 20; códigos de jornada (684, 795) → None
    dia_num = _parse_day_number(raw_data)
    if dia_num is None:
        return None

    # Verifica se algum dia desse número cabe no intervalo
    period_dr = pd.date_range(start=period_start, end=period_end, freq='D')
    for d in period_dr:
        if d.day == dia_num:
            return True
    return False


def _entity_bbox(entity):
    try:
        verts = entity.page_anchor.page_refs[0].bounding_poly.normalized_vertices
        xs = [v.x for v in verts if v.x is not None]
        ys = [v.y for v in verts if v.y is not None]
        if not xs or not ys:
            return None
        return (min(xs), min(ys), max(xs), max(ys))
    except Exception:
        return None


def _bbox_overlap_ratio(bbox_a, bbox_b):
    if not bbox_a or not bbox_b:
        return 0.0
    ax_min, ay_min, ax_max, ay_max = bbox_a
    bx_min, by_min, bx_max, by_max = bbox_b
    inter_x = max(0.0, min(ax_max, bx_max) - max(ax_min, bx_min))
    inter_y = max(0.0, min(ay_max, by_max) - max(ay_min, by_min))
    inter_area = inter_x * inter_y
    a_area = max(0.0, ax_max - ax_min) * max(0.0, ay_max - ay_min)
    if a_area <= 0:
        return 0.0
    return inter_area / a_area


# ─────────────────────────────────────────────────────────────────────────────
# Gemini: extração de períodos
# ─────────────────────────────────────────────────────────────────────────────

def _gemini_extract_period(pdf_path, page_idx, page_number, quinzenas_nao_sequenciais=False):
    tmp_path = None
    uploaded_file = None
    try:
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        writer.add_page(reader.pages[page_idx])

        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            writer.write(tmp.name)
            tmp_path = tmp.name

        uploaded_file = _gemini.files.upload(file=tmp_path)

        f = _gemini.files.get(name=uploaded_file.name)
        waited = 0
        while f.state.name == 'PROCESSING' and waited < 30:
            time.sleep(1)
            waited += 1
            f = _gemini.files.get(name=uploaded_file.name)

        if quinzenas_nao_sequenciais:
            prompt = """Este documento é UMA PÁGINA de cartão de ponto que pode conter MAIS DE UMA tabela de marcações com períodos diferentes/não-sequenciais.

Identifique TODAS as tabelas de marcações de ponto visíveis nesta página. Para CADA tabela, retorne:
- start_date: PRIMEIRA data de registro daquela tabela específica (DD/MM/YYYY)
- end_date: ÚLTIMA data de registro daquela tabela específica (DD/MM/YYYY)
- bbox: bounding box da tabela em coordenadas normalizadas [x_min, y_min, x_max, y_max] (valores entre 0.0 e 1.0)
- label: rótulo curto identificando a tabela (ex: "1ª Quinzena", "Tabela superior", "Período A", etc.)

Se houver SOMENTE 1 tabela na página, retorne array com 1 item.
Se houver 2+ tabelas com períodos diferentes, retorne todas separadamente.

Retorne APENAS um JSON válido, sem markdown, sem explicações:
{"periods": [{"start_date": "DD/MM/YYYY", "end_date": "DD/MM/YYYY", "bbox": [0.0, 0.0, 1.0, 0.5], "label": "..."}], "confidence": "high"}

Use confidence "low" se houver datas ilegíveis. Se nenhuma tabela for identificável: {"periods": [], "confidence": "low"}"""
        else:
            prompt = """Este documento é um cartão de ponto ou relatório de marcações de ponto de funcionário.

Leia a página inteira de cima para baixo e identifique a PRIMEIRA e a ÚLTIMA data de registro de ponto visíveis nesta folha.

Retorne APENAS um JSON válido, sem texto adicional, sem markdown, sem explicações:
{"start_date": "DD/MM/YYYY", "end_date": "DD/MM/YYYY", "confidence": "high"}

Use confidence "low" se as datas estiverem ilegíveis ou ambíguas.
Se não encontrar nenhuma data de ponto, retorne: {"start_date": null, "end_date": null, "confidence": "low"}"""

        response = _gemini.models.generate_content(
            model=GEMINI_MODEL,
            contents=[f, prompt]
        )

        raw = response.text.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        result = json.loads(raw)

        if quinzenas_nao_sequenciais:
            periods = result.get('periods', [])
            conf    = result.get('confidence', 'low')

            normalized_periods = []
            for p in periods:
                start = p.get('start_date')
                end   = p.get('end_date')
                bbox  = p.get('bbox')
                label = p.get('label', '')

                if not start or not end:
                    continue

                start = start.replace('-', '/').replace('.', '/')
                end   = end.replace('-', '/').replace('.', '/')

                if not bbox or len(bbox) != 4:
                    bbox = [0.0, 0.0, 1.0, 1.0]
                else:
                    try:
                        bbox = [float(v) for v in bbox]
                        bbox = [max(0.0, min(1.0, v)) for v in bbox]
                    except (TypeError, ValueError):
                        bbox = [0.0, 0.0, 1.0, 1.0]

                normalized_periods.append({
                    'start_date': start,
                    'end_date':   end,
                    'bbox':       bbox,
                    'label':      label,
                })

            if not normalized_periods:
                return None

            return {
                'multi':      True,
                'periods':    normalized_periods,
                'confidence': conf,
            }
        else:
            start = result.get('start_date')
            end   = result.get('end_date')
            conf  = result.get('confidence', 'low')

            if start and end:
                start = start.replace('-', '/').replace('.', '/')
                end   = end.replace('-', '/').replace('.', '/')
                return {
                    'start_date': start,
                    'end_date':   end,
                    'confidence': conf
                }
            return None

    except Exception as ex:
        print(f"[ERR ] Gemini período pág {page_number}: {ex}", flush=True)
        return None
    finally:
        if uploaded_file:
            try:
                _gemini.files.delete(name=uploaded_file.name)
            except Exception:
                pass
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Tarefas RQ
# ─────────────────────────────────────────────────────────────────────────────

def extract_periods_task(pdf_path, pages, user_id, quinzenas_nao_sequenciais=False):
    job = get_current_job()
    if not job:
        return None
    job.meta['user_id'] = user_id
    job.save_meta()

    t_inicio = time.time()

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
        LOG_SEP('EXTRAÇÃO DE PERÍODOS')
        LOG('arquivo',          os.path.basename(pdf_path))
        LOG('total págs pdf',   f"{total_pdf} páginas")
        LOG('páginas selecionadas', f"{total_selected}")
        LOG('modelo',           f"Gemini {GEMINI_MODEL}  (paralelo, max {MAX_GEMINI_WORKERS} workers)")
        if quinzenas_nao_sequenciais:
            LOG('modo especial', 'múltiplas tabelas por página ativado')

        job.meta.update({
            'status': 'processing',
            'message': f'Enviando {total_selected} páginas para análise...',
            'current_step': 0,
            'total_steps': total_selected
        })
        job.save_meta()

        results = {}
        completed_count = 0

        with ThreadPoolExecutor(max_workers=min(MAX_GEMINI_WORKERS, total_selected)) as executor:
            futures = {
                executor.submit(
                    _gemini_extract_period,
                    pdf_path,
                    page_idx,
                    page_idx + 1,
                    quinzenas_nao_sequenciais
                ): page_idx
                for page_idx in indices
            }

            for future in as_completed(futures):
                page_idx = futures[future]
                period   = future.result()
                results[page_idx] = period

                completed_count += 1

                if period is None:
                    LOG(f"pág {page_idx + 1}", "sem período identificado", 'WARN')
                elif period.get('multi'):
                    n_periods = len(period.get('periods', []))
                    conf      = period.get('confidence', 'low')
                    conf_tag  = '' if conf == 'high' else '  ⚠ low confidence'
                    LOG(f"pág {page_idx + 1}",
                        f"{n_periods} tabela(s) detectada(s){conf_tag}")
                    for i, p in enumerate(period['periods'], start=1):
                        LOG(f"  tabela {i}",
                            f"{p['start_date']} → {p['end_date']}  "
                            f"bbox={[round(v,2) for v in p['bbox']]}  '{p.get('label','')}'")
                else:
                    conf_tag = '' if period.get('confidence') == 'high' else '  ⚠ low confidence'
                    LOG(f"pág {page_idx + 1}",
                        f"{period['start_date']} → {period['end_date']}{conf_tag}")

                job.meta.update({
                    'message': f'Processando {completed_count}/{total_selected} páginas...',
                    'current_step': completed_count
                })
                job.save_meta()

        res = []
        sem_periodo = []
        low_conf    = []

        for page_idx in sorted(indices):
            period = results.get(page_idx)
            page_number = page_idx + 1

            if period is None:
                sem_periodo.append(page_number)
                res.append({
                    'page_number': page_number,
                    'page_index':  page_idx,
                    'period':      None,
                    'bbox':        None,
                    'label':       '',
                    'region_id':   0,
                })
                continue

            if period.get('multi'):
                conf = period.get('confidence', 'low')
                if conf == 'low':
                    low_conf.append(page_number)
                for i, p in enumerate(period['periods']):
                    res.append({
                        'page_number': page_number,
                        'page_index':  page_idx,
                        'period':      {
                            'start_date': p['start_date'],
                            'end_date':   p['end_date'],
                            'confidence': conf,
                        },
                        'bbox':        p['bbox'],
                        'label':       p.get('label', ''),
                        'region_id':   i,
                    })
            else:
                if period.get('confidence') == 'low':
                    low_conf.append(page_number)
                res.append({
                    'page_number': page_number,
                    'page_index':  page_idx,
                    'period':      period,
                    'bbox':        None,
                    'label':       '',
                    'region_id':   0,
                })

        t_total = round(time.time() - t_inicio, 1)
        LOG_SEP('RESULTADO')
        LOG('páginas processadas',    f"{total_selected - len(sem_periodo)} de {total_selected}")
        LOG('total de regiões',       f"{len(res)} entrada(s) (cada região conta separadamente)")
        if sem_periodo:
            LOG('sem período identificado', str(sem_periodo), 'WARN')
        if low_conf:
            LOG('low confidence (revisar)', str(low_conf), 'WARN')
        LOG('tempo total',            f"{t_total}s")
        LOG_SEP()

        job.meta.update({'status': 'completed', 'result': res, 'pdf_path': pdf_path})
        job.save()
        return res

    except Exception:
        err = traceback.format_exc()
        print(f"[ERR ] [extract_periods_task] {err}", flush=True)
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
    t_inicio   = time.time()

    try:
        valid_pages = pages_json

        pdf_size_mb    = round(os.path.getsize(pdf_path) / (1024 * 1024), 1)
        pdf_nome       = job.meta.get('original_filename', os.path.basename(pdf_path))
        reader_info    = PdfReader(pdf_path)
        pdf_total_pags = len(reader_info.pages)
        worker_pid     = os.getpid()
        modelo_desc    = '6 — com data (geral_ai)' if model_type == '6' else '7 — sem data (geral)'
        rpm_uso_agora  = _get_rpm_usage()
        slots_livres   = DOCAI_RPM_LIMIT - rpm_uso_agora

        unique_pages = len({p['page_index'] for p in valid_pages})
        total_regioes = len(valid_pages)

        LOG_SEP('JOB INICIADO')
        LOG('job_id',             job.id)
        LOG('usuário',            user_id)
        LOG('worker PID',         str(worker_pid))
        LOG('modelo',             modelo_desc)
        LOG('arquivo',            pdf_nome)
        LOG('tamanho do pdf',     f"{pdf_size_mb} MB")
        LOG('total págs pdf',     f"{pdf_total_pags} páginas")
        LOG('regiões a processar', f"{total_regioes} região(ões) em {unique_pages} página(s)")
        if job.meta.get('turno_noturno'):
            LOG('modo especial',  'turno noturno ativado')
        if total_regioes > unique_pages:
            LOG('modo especial',  'múltiplas regiões por página (filtro por data)')
        LOG_SEP('Limite DocAI')
        LOG('limite configurado', f"{DOCAI_RPM_LIMIT} req/min  (margem segura — cota Google: 240)")
        LOG('uso global agora',
            f"{rpm_uso_agora} / {DOCAI_RPM_LIMIT} req no último minuto"
            + ("  ⚠ próximo do limite" if rpm_uso_agora >= DOCAI_RPM_LIMIT * 0.8 else ""))
        LOG('slots disponíveis',
            f"{slots_livres} livres  — "
            + ("sem espera prevista" if slots_livres >= unique_pages
               else f"pode aguardar: {unique_pages} necessários, {slots_livres} livres agora"))

        # ── 1. Validação ──────────────────────────────────────────────────────
        LOG_SEP('Períodos confirmados pelo usuário')

        pages_validas   = []
        pages_ignoradas = []

        for p in valid_pages:
            pnum = p.get('page_number', '?')
            label_extra = f"  [{p.get('label','')}]" if p.get('label') else ""
            try:
                start_dt = datetime.strptime(p['period']['start_date'], '%d/%m/%Y')
                end_dt   = datetime.strptime(p['period']['end_date'],   '%d/%m/%Y')
                if end_dt < start_dt:
                    motivo = (f"end_date '{p['period']['end_date']}' < start_date "
                              f"'{p['period']['start_date']}'")
                    LOG(f"pág {pnum}{label_extra}",
                        f"{p['period']['start_date']} → {p['period']['end_date']}  "
                        f"IGNORADA: {motivo}", 'WARN')
                    pages_ignoradas.append((pnum, motivo))
                    continue
                dias = len(pd.date_range(start=start_dt, end=end_dt, freq='D'))
                LOG(f"pág {pnum}{label_extra}",
                    f"{p['period']['start_date']} → {p['period']['end_date']}  ({dias} dias)")
                p['start_dt'] = start_dt
                p['end_dt']   = end_dt
                pages_validas.append(p)
            except (ValueError, TypeError, KeyError) as ve:
                motivo = f"data inválida: {ve}"
                LOG(f"pág {pnum}{label_extra}", f"IGNORADA: {motivo}", 'WARN')
                pages_ignoradas.append((pnum, motivo))

        LOG('regiões válidas', f"{len(pages_validas)} de {len(valid_pages)}")

        if not pages_validas:
            raise ValueError("Nenhuma região com período válido após validação.")

        pages_validas = sorted(pages_validas, key=lambda p: p['start_dt'])
        global_start  = min(p['start_dt'] for p in pages_validas)
        global_end    = max(p['end_dt']   for p in pages_validas)

        LOG('período global',
            f"{global_start.strftime('%d/%m/%Y')} → {global_end.strftime('%d/%m/%Y')}")

        # ── 2. Calendário mestre ──────────────────────────────────────────────
        full_range = pd.date_range(start=global_start, end=global_end, freq='D')
        master_df  = pd.DataFrame({
            'Dia':      full_range.strftime('%d/%m/%Y'),
            'Dia_Sema': full_range.weekday.map(day_map_pt)
        })
        for i in range(1, 12):
            master_df[f'Entrada{i}'] = "0"
            master_df[f'Saida{i}']   = "0"

        date_to_row = {row['Dia']: idx for idx, row in master_df.iterrows()}
        LOG('calendário mestre',
            f"{len(master_df)} dias  "
            f"({master_df['Dia'].iloc[0]} → {master_df['Dia'].iloc[-1]})")

        # ── 3. Document AI ────────────────────────────────────────────────────
        LOG_SEP('Document AI')
        LOG('requisições a enviar',
            f"{unique_pages} páginas únicas  "
            f"(max_workers={min(MAX_DOCAI_WORKERS, unique_pages)})")

        t_docai_inicio = time.time()
        results_by_order, total_waited, index_to_order = extractor.process_pdf_parallel(
            pdf_path, pages_validas, job.id
        )
        t_docai_seg = round(time.time() - t_docai_inicio, 1)

        LOG('tempo de resposta DocAI', f"{t_docai_seg}s")
        if total_waited > 0:
            LOG('aguardou rate limit', f"{total_waited}s no total", 'WARN')
        else:
            LOG('espera por rate limit', 'nenhuma — limite não atingido')

        rpm_uso_apos = _get_rpm_usage()
        LOG('uso global após envio',
            f"{rpm_uso_apos} / {DOCAI_RPM_LIMIT} req no último minuto")

        ent_por_pag_partes  = []
        paginas_sem_retorno = []
        for page_idx_unique in sorted(index_to_order.keys()):
            order = index_to_order[page_idx_unique]
            entities_pag, _ = results_by_order[order]
            n    = len(entities_pag)
            ent_por_pag_partes.append(f"pág {page_idx_unique + 1}: {n}")
            if n == 0:
                paginas_sem_retorno.append(page_idx_unique + 1)

        LOG('entidades por página', ' · '.join(ent_por_pag_partes))
        if paginas_sem_retorno:
            LOG('págs sem retorno',
                f"{paginas_sem_retorno} — em branco ou formato não reconhecido",
                'WARN')

        # ── 4. Preenchimento do CSV ───────────────────────────────────────────
        extractor.update_progress(4, 4, "Finalizando planilha...")

        filled_count          = 0
        skip_no_date          = 0
        skip_no_row           = 0
        skip_duplicado        = 0
        continuacoes_mescladas = 0
        inferidas_por_y       = 0
        full_date_hits        = 0
        day_month_hits        = 0
        fallback_day_hits     = 0
        regioes_filtradas     = 0
        valores_invalidos     = 0  # contador de horários impossíveis rejeitados

        _infer_warn: dict[int, list] = {}

        for region_idx, p_info in enumerate(pages_validas):
            page_idx = p_info['page_index']
            order = index_to_order.get(page_idx)
            if order is None:
                continue

            entities_pag_all, _ = results_by_order.get(order, ([], ""))

            # ── ALTERAÇÃO: filtra por DATA do dia (não por bbox) ──────────────
            # Se a página tem múltiplas regiões (mesma page_index aparece >1 vez),
            # filtramos as entidades pelo dia (1-31) que cabe no período da região.
            page_idx_count = sum(1 for pp in pages_validas if pp['page_index'] == page_idx)

            if page_idx_count > 1:
                # Múltiplas regiões nesta página → filtra por data
                entities_pag = []
                descartadas = 0
                for ent in entities_pag_all:
                    pertence = _entity_falls_in_period(
                        ent, p_info['start_dt'], p_info['end_dt'], p_info['start_dt'].year
                    )
                    if pertence is True:
                        entities_pag.append(ent)
                    elif pertence is False:
                        descartadas += 1
                    else:
                        # None = sem data extraível → inclui (vai cair em skip_no_date)
                        entities_pag.append(ent)
                regioes_filtradas += descartadas
                label_extra = f"  [{p_info.get('label','')}]" if p_info.get('label') else ""
                LOG(f"pág {page_idx+1}{label_extra}",
                    f"{len(entities_pag)} entidades dentro do período "
                    f"(de {len(entities_pag_all)} totais — {descartadas} descartadas por data)")
            else:
                # Página com região única → usa todas as entidades
                entities_pag = entities_pag_all

            page_dr    = pd.date_range(start=p_info['start_dt'], end=p_info['end_dt'], freq='D')
            page_dates = [d.strftime('%d/%m/%Y') for d in page_dr]
            default_year = p_info['start_dt'].year

            page_row_ptr = 0

            for entity in entities_pag:
                shard_text = getattr(entity, '_shard_text', '')
                data = {
                    prop.type_.lower(): get_text_safely(prop, shard_text)
                    for prop in entity.properties
                }

                raw_dia = data.get('dia', data.get('data', ''))

                target_date = None

                # Etapa 1: data completa
                full_date = extract_full_date(raw_dia)
                if full_date and full_date in date_to_row:
                    target_date = full_date
                    full_date_hits += 1
                    if full_date in page_dates:
                        new_ptr = page_dates.index(full_date)
                        if new_ptr >= page_row_ptr:
                            page_row_ptr = new_ptr + 1

                # Etapa 2: DD/MM
                if target_date is None and raw_dia:
                    match_dm = re.match(r'^(\d{1,2})[/.-](\d{1,2})$', str(raw_dia).strip())
                    if match_dm:
                        d, m = match_dm.groups()
                        years_range = list(range(p_info['start_dt'].year,
                                                  p_info['end_dt'].year + 1))
                        for year in years_range:
                            candidate = f"{d.zfill(2)}/{m.zfill(2)}/{year}"
                            if candidate in date_to_row and candidate in page_dates:
                                target_date = candidate
                                day_month_hits += 1
                                new_ptr = page_dates.index(candidate)
                                if new_ptr >= page_row_ptr:
                                    page_row_ptr = new_ptr + 1
                                break
                
                raw_dia = data.get('dia', data.get('data', ''))

                target_date = None

                # Etapa 1: data completa DD/MM/YYYY (raro mas se vier, é confiável)
                full_date = extract_full_date(raw_dia)
                if full_date and full_date in date_to_row:
                    target_date = full_date
                    full_date_hits += 1
                    if full_date in page_dates:
                        new_ptr = page_dates.index(full_date)
                        if new_ptr >= page_row_ptr:
                            page_row_ptr = new_ptr + 1

                # Etapa 2: DD/MM com ano da página
                if target_date is None and raw_dia:
                    match_dm = re.match(r'^(\d{1,2})[/.-](\d{1,2})$', str(raw_dia).strip())
                    if match_dm:
                        d, m = match_dm.groups()
                        years_range = list(range(p_info['start_dt'].year,
                                                  p_info['end_dt'].year + 1))
                        for year in years_range:
                            candidate = f"{d.zfill(2)}/{m.zfill(2)}/{year}"
                            if candidate in date_to_row and candidate in page_dates:
                                target_date = candidate
                                day_month_hits += 1
                                new_ptr = page_dates.index(candidate)
                                if new_ptr >= page_row_ptr:
                                    page_row_ptr = new_ptr + 1
                                break

                # Etapa 3 (NOVA PRIORIDADE): número do dia (1-31) extraído pelo DocAI
                # Esta etapa vem ANTES da inferência por Y porque é mais confiável.
                # O DocAI extrai o número do dia em quase todas as linhas — usar isso
                # evita problemas quando as entidades vêm fora de ordem.
                # Etapa 3: nº do dia pelo DocAI — helper trata artefato OCR '1XX'
                if target_date is None and raw_dia:
                    n = _parse_day_number(raw_dia)
                    if n is not None:
                        day_str   = f"{n:02d}"
                        # Procura primeira data do período da página com esse dia
                        day_match = next(
                            (d for d in page_dates if d.startswith(day_str + '/')),
                            None
                        )
                        if day_match and day_match in date_to_row:
                            target_date = day_match
                            fallback_day_hits += 1
                            new_ptr = page_dates.index(day_match)
                            if new_ptr >= page_row_ptr:
                                page_row_ptr = new_ptr + 1

                # Etapa 4 (ÚLTIMO FALLBACK): inferência por posição Y
                # Só usa quando nem o número do dia foi extraído (raro)
                if target_date is None:
                    if page_row_ptr < len(page_dates):
                        expected_date = page_dates[page_row_ptr]
                        inferred = infer_date_by_position(raw_dia or None, expected_date, default_year)
                        if inferred in date_to_row:
                            target_date = inferred
                            inferidas_por_y += 1
                            page_row_ptr += 1
                            pn = p_info['page_number']
                            if raw_dia:
                                _infer_warn.setdefault(pn, []).append(f"'{raw_dia}'→'{inferred}'")
                            else:
                                _infer_warn.setdefault(pn, []).append(f"ausente→'{inferred}'")

                if target_date is None:
                    skip_no_date += 1
                    # Não avança o ponteiro Y aqui — entidades sem data não devem
                    # corromper o tracker para as próximas
                    continue

                target_idx = date_to_row.get(target_date)
                if target_idx is None:
                    skip_no_row += 1
                    continue

                # Conta horários inválidos antes de preencher
                for k in range(1, 12):
                    raw_e = data.get(f'entrada{k}', "0")
                    raw_s = data.get(f'saida{k}', "0")
                    if raw_e and raw_e != "0" and normalize_time(raw_e) == "0":
                        valores_invalidos += 1
                    if raw_s and raw_s != "0" and normalize_time(raw_s) == "0":
                        valores_invalidos += 1

                if master_df.at[target_idx, 'Entrada1'] == "0":
                    preencheu = _fill_slots(master_df, target_idx, data)
                    if preencheu:
                        filled_count += 1
                else:
                    if _is_duplicate_values(master_df, target_idx, data):
                        skip_duplicado += 1
                    elif _has_empty_slots(master_df, target_idx):
                        preencheu = _fill_slots(master_df, target_idx, data)
                        if preencheu:
                            continuacoes_mescladas += 1
                    else:
                        skip_duplicado += 1

        for _pn, _itens in sorted(_infer_warn.items()):
            LOG(f"  inferência Y pág {_pn}",
                f"{len(_itens)} datas corrigidas/inferidas por posição  "
                f"(ex: {_itens[0]})", 'WARN')

        if regioes_filtradas > 0:
            LOG('entidades fora dos períodos', f"{regioes_filtradas} (filtradas por data)")
        if valores_invalidos > 0:
            LOG('horários inválidos rejeitados',
                f"{valores_invalidos} (OCR retornou valores impossíveis tipo 20:70, 40:74)", 'WARN')

        # ── 4.5. Pareamento noturno ───────────────────────────────────────────
        avisos_noturno = []
        pareados_noturno = 0
        if job.meta.get('turno_noturno'):
            try:
                from noturno_pareamento import aplicar_pareamento_noturno
                LOG_SEP('Pareamento de plantões noturnos')
                resultado_noturno = aplicar_pareamento_noturno(master_df, log_fn=LOG)
                avisos_noturno = resultado_noturno.get('avisos', [])
                pareados_noturno = resultado_noturno.get('pareados', 0)
                LOG('plantões pareados', str(pareados_noturno))
                LOG('avisos gerados',   str(len(avisos_noturno)))
            except Exception as e:
                LOG('erro no pareamento noturno', str(e), 'WARN')

        # ── 5. Salvar CSV ─────────────────────────────────────────────────────
        random_id      = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        final_filename = f"Ponto_Extraido_{random_id}.csv"
        out_path       = os.path.join(tempfile.gettempdir(), f"{job.id}.csv")
        master_df.to_csv(out_path, index=False, sep=';', encoding='utf-8-sig')
        csv_size_kb = round(os.path.getsize(out_path) / 1024, 1)

        dias_preenchidos = int((master_df['Entrada1'] != "0").sum())
        # Inclui dias com só Saida1 (caso do dia 01 com saída órfã)
        dias_com_alguma_marcacao = int(((master_df['Entrada1'] != "0") | (master_df['Saida1'] != "0")).sum())
        taxa       = round((dias_com_alguma_marcacao / len(master_df)) * 100, 1) if len(master_df) > 0 else 0
        taxa_aviso = taxa < 30 and dias_com_alguma_marcacao > 0

        LOG_SEP('Resultado do preenchimento')
        LOG('dias com marcação',
            f"{dias_com_alguma_marcacao} / {len(master_df)}  (taxa: {taxa}%)"
            + ("  ⚠ ABAIXO DO LIMIAR (30%)" if taxa_aviso else ""))
        LOG('resolução data completa', f"{full_date_hits}")
        LOG('resolução DD/MM + ano página', f"{day_month_hits}")
        LOG('resolução nº do dia (DocAI)', f"{fallback_day_hits}  (campo `data` extraído pelo DocAI)")
        LOG('inferidas por posição Y', f"{inferidas_por_y}  (último fallback, quando DocAI não extraiu nº)")
        LOG('continuações mescladas', f"{continuacoes_mescladas}")
        LOG('duplicados ignorados', f"{skip_duplicado}")
        LOG('skip fora do range',   str(skip_no_row))
        LOG('skip sem data',        str(skip_no_date))
        if taxa_aviso:
            LOG('avaliação',
                'taxa baixa — verifique se as datas informadas correspondem ao PDF',
                'WARN')
        elif paginas_sem_retorno:
            LOG('avaliação',
                f"resultado pode estar incompleto — págs {paginas_sem_retorno} sem retorno",
                'WARN')
        else:
            LOG('avaliação',
                'taxa normal — dias sem marcação são folgas/feriados esperados')

        t_total = round(time.time() - t_inicio, 1)

        LOG_SEP('JOB CONCLUÍDO')
        LOG('job_id',      job.id)
        LOG('tempo total',
            f"{t_total}s  (DocAI: {t_docai_seg}s"
            + (f", aguardou rate limit: {total_waited}s" if total_waited > 0 else "") + ")")
        LOG('arquivo',     f"{final_filename}  ({csv_size_kb} KB)")
        LOG_SEP()

        total_dias = len(master_df)
        job.meta.update({
            'status':     'completed',
            'file_path':  out_path,
            'filename':   final_filename,
            'avisos':     avisos_noturno,
            'total_dias': total_dias,
            'pareados':   pareados_noturno,
        })
        job.save()
        return out_path

    except Exception:
        err     = traceback.format_exc()
        t_total = round(time.time() - t_inicio, 1)
        LOG_SEP('JOB FALHOU')
        LOG('job_id',      job.id)
        LOG('tempo total', f"{t_total}s")
        LOG('erro',        err.strip().split('\n')[-1], 'ERR ')
        LOG_SEP()
        print(err, flush=True)
        job.meta.update({'status': 'error', 'error': err})
        job.save()
        return None
