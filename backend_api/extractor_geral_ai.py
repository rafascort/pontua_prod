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

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÕES
# ─────────────────────────────────────────────────────────────────────────────
MAX_DOCAI_WORKERS  = 60
MAX_GEMINI_WORKERS = 20           # paralelo para extração de períodos
DOCAI_RPM_LIMIT    = 100          # margem segura — cota real Google: 120/min
DOCAI_RATE_KEY     = 'docai_sliding_window'
_redis = redis_lib.Redis(host='localhost', port=6379, db=0)

# Cliente Gemini — mesmo usado pelo payroll_extractor_ai
_gemini = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
GEMINI_MODEL = 'gemini-2.5-flash'
# ─────────────────────────────────────────────────────────────────────────────


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
# ─────────────────────────────────────────────────────────────────────────────


# ─── RATE LIMITER GLOBAL (sliding window no Redis) ───────────────────────────
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

    def spatial_sort_entities(self, entities):
        """
        Ordena entidades tabela_marcacoes pela posição vertical (Y) na página.
        Vem do código antigo — essencial para saber a ordem física das linhas.
        """
        rows = [e for e in entities
                if e.type_.lower() == 'tabela_marcacoes']

        def get_y(e):
            try:
                return e.page_anchor.page_refs[0].bounding_poly.normalized_vertices[0].y
            except Exception:
                return 0.0

        return sorted(rows, key=get_y)

    def _process_single_page(self, pdf_bytes_single: bytes, page_order: int, job_id: str):
        """
        Envia UMA página ao DocAI após adquirir slot no rate limiter global.
        Retorna entidades ordenadas por Y (spatial_sort já aplicado aqui).
        """
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
            # Ordena por Y imediatamente ao receber — cada página já chega ordenada
            sorted_ents = self.spatial_sort_entities(doc.entities)
            return page_order, sorted_ents, doc_text, slot_num, waited
        except Exception as ex:
            print(f"[ERR ] Página {page_order} falhou no Document AI: {ex}", flush=True)
            return page_order, [], "", slot_num, waited

    def process_pdf_parallel(self, pdf_path: str, valid_pages: list, job_id: str):
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

        self.update_progress(1, 4, f"Enviando {total} página(s) para o Google...")

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
                    f"Google processou {completed}/{total} página(s)..."
                )

        self.update_progress(3, 4, "Consolidando resultados...")
        return results, round(total_waited, 1)


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


def normalize_date(date_str, default_year):
    """
    Vem do código antigo. Normaliza vários formatos de data para DD/MM/YYYY.
    Suporta DD/MM, DD/MM/YY, DD/MM/YYYY, separadores ponto e hífen.
    """
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
            # valida se é uma data possível
            datetime.strptime(f"{day}/{month}/{year}", '%d/%m/%Y')
            return f"{day}/{month}/{year}"
        except ValueError:
            return None
    return None


def extract_full_date(raw):
    """Retorna DD/MM/YYYY se o campo já contém data completa, senão None."""
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
    """
    Tenta corrigir/inferir a data usando a data esperada por posição Y.

    Casos cobertos:
    - DocAI retornou vazio/None → usa expected_date diretamente
    - DocAI leu dígito parcial (ex: "7" quando esperado é "17") → corrige
    - DocAI leu DD/MM sem ano → valida contra expected_date e completa
    - DocAI leu data coerente com a esperada → confirma

    Retorna a data corrigida como DD/MM/YYYY, ou expected_date como fallback.
    """
    if not data_ia:
        # Cenário 1/2: dado completamente ausente → inferência por posição
        return expected_date

    normalized = normalize_date(data_ia, default_year)

    if normalized == expected_date:
        return normalized

    if normalized:
        ai_day  = normalized.split('/')[0].lstrip('0') or '0'
        exp_day = expected_date.split('/')[0].lstrip('0') or '0'

        # Correção de dígito parcial: DocAI leu "7" mas esperado é "17"
        # Vem do código antigo — o OCR às vezes perde o primeiro dígito
        if len(ai_day) == 1 and exp_day.endswith(ai_day):
            ai_rest  = normalized[2:]    # /MM/YYYY ou /MM
            exp_rest = expected_date[2:]
            # mês e ano do esperado devem bater
            if ai_rest.startswith(exp_rest[:3]):
                return expected_date

        # DocAI leu data completa diferente — confia no DocAI, não na posição
        if len(normalized) == 10:
            return normalized

    # Último recurso: usa posição
    return expected_date


def _fill_slots(master_df, target_idx, data):
    """
    Preenche os slots de Entrada/Saida no master_df para um dado target_idx.
    Sempre busca o próximo slot vazio — nunca sobrescreve.
    Retorna True se pelo menos um slot foi preenchido.

    FIX: Em páginas de continuação (mescla), o DocAI às vezes retorna horários
    de SAÍDA no campo entrada1 (e.g., a saída do almoço 12:00 vem como entrada1
    em vez de saida1). Para corrigir isso, quando um e_val chega sem s_val,
    verificamos se existe uma entrada "órfã" (Entrada{c} preenchida, Saida{c}
    vazia) cujo horário é menor que e_val — nesse caso o e_val é na verdade
    uma saída disfarçada e vai para Saida{c}.

    Comportamento:
    - s_val presente: preenche no próximo Saida slot vazio (independente)
    - e_val presente + entrada órfã com e_val > entrada_c: preenche Saida{c}
    - e_val presente + sem órfã elegível: preenche próximo Entrada slot vazio
    """
    preencheu = False
    for k in range(1, 12):
        e_val = normalize_time(data.get(f'entrada{k}', data.get(f'entrada_{k}', "0")))
        s_val = normalize_time(data.get(f'saida{k}',   data.get(f'saída{k}',   "0")))

        if e_val == "0" and s_val == "0":
            continue

        # Saida explícita: preenche no próximo slot Saida vazio (comportamento original)
        if s_val != "0":
            for c in range(1, 12):
                if master_df.at[target_idx, f'Saida{c}'] == "0":
                    master_df.at[target_idx, f'Saida{c}'] = s_val
                    preencheu = True
                    break

        if e_val != "0":
            # FIX: procura entrada "órfã" (Entrada preenchida, Saida vazia)
            # onde e_val é posterior — indica que e_val é na verdade uma saída
            colocado_como_saida = False
            for c in range(1, 12):
                entrada_c = master_df.at[target_idx, f'Entrada{c}']
                saida_c   = master_df.at[target_idx, f'Saida{c}']
                if entrada_c != "0" and saida_c == "0" and e_val > entrada_c:
                    # Horário posterior a uma entrada sem saída → é uma saída
                    master_df.at[target_idx, f'Saida{c}'] = e_val
                    preencheu = True
                    colocado_como_saida = True
                    break

            if not colocado_como_saida:
                # Valor é realmente uma entrada — preenche no próximo slot vazio
                for c in range(1, 12):
                    if master_df.at[target_idx, f'Entrada{c}'] == "0":
                        master_df.at[target_idx, f'Entrada{c}'] = e_val
                        preencheu = True
                        break

    return preencheu


def _has_empty_slots(master_df, target_idx):
    """
    Retorna True se ainda existe algum slot vazio (Entrada ou Saida) na linha.
    Usado para distinguir continuação de duplicata.
    """
    for c in range(1, 12):
        if master_df.at[target_idx, f'Entrada{c}'] == "0":
            return True
        if master_df.at[target_idx, f'Saida{c}'] == "0":
            return True
    return False


def _is_duplicate_values(master_df, target_idx, data):
    """
    Verifica se todos os valores não-zero da entidade entrante já existem
    nos slots preenchidos da linha.

    Necessário para distinguir dois casos que parecem iguais para _has_empty_slots:
    - Página dividida (continuação real): entidade tem E2/S2 novos → mescla
    - Período duplicado (duas páginas com mesmo período): entidade repete
      E1/S1 que já estão preenchidos → skip, não preenche E3/S3 com lixo

    FIX: Compara e_val contra o conjunto UNIFICADO de entradas + saídas já
    presentes. Sem este fix, um e_val=12:00 vindo do DocAI (que na verdade é
    uma saída já registrada em Saida1=12:00) não era reconhecido como duplicata
    porque a verificação era feita apenas contra existing_entradas, não contra
    existing_saidas — resultando no valor sendo inserido em Entrada2.

    Retorna True se for duplicata (todos os valores já existem).
    """
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
    # FIX: união de todos os valores já presentes, independente de serem
    # entrada ou saída — o DocAI de páginas de continuação mistura os dois
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

    return not has_new_value  # True = todos os valores já existem = duplicata


def _gemini_extract_period(pdf_path, page_idx, page_number):
    """
    Envia UMA página ao Gemini e retorna o período (start_date, end_date).

    - Sobe a página como PDF de 1 página (não JPEG — qualidade nativa)
    - Gemini lê a página inteira, não só o cabeçalho
    - Prompt pede primeira e última data visíveis no cartão de ponto
    - Retorna dict com start_date/end_date em DD/MM/YYYY, ou None se falhar

    O page_order é controlado externamente pelo ThreadPoolExecutor —
    o resultado é sempre vinculado ao page_idx correto no dict de resultados.
    """
    tmp_path = None
    uploaded_file = None
    try:
        # Extrai página como PDF de 1 página
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        writer.add_page(reader.pages[page_idx])

        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            writer.write(tmp.name)
            tmp_path = tmp.name

        # Upload para o Gemini Files API
        uploaded_file = _gemini.files.upload(file=tmp_path)

        # Aguarda o arquivo estar pronto
        f = _gemini.files.get(name=uploaded_file.name)
        waited = 0
        while f.state.name == 'PROCESSING' and waited < 30:
            time.sleep(1)
            waited += 1
            f = _gemini.files.get(name=uploaded_file.name)

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

        # Extrai JSON da resposta — remove markdown se vier com ```
        raw = response.text.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        result = json.loads(raw)

        start = result.get('start_date')
        end   = result.get('end_date')
        conf  = result.get('confidence', 'low')

        if start and end:
            # Normaliza para DD/MM/YYYY (Gemini às vezes retorna com traço)
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

def extract_periods_task(pdf_path, pages, user_id):
    """
    Extrai o período (primeira e última data) de cada página selecionada
    usando Gemini em paralelo.

    Garante ordem correta: cada future é mapeado ao seu page_idx original
    via dict results{page_idx: period}. Independente da ordem de chegada
    das respostas, o resultado final é ordenado por page_idx.
    """
    job = get_current_job()
    if not job:
        return None
    job.meta['user_id'] = user_id
    job.save_meta()

    t_inicio = time.time()

    try:
        reader    = PdfReader(pdf_path)
        total_pdf = len(reader.pages)

        # Monta lista de índices a partir do range recebido
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

        job.meta.update({
            'status': 'processing',
            'message': f'Enviando {total_selected} páginas ao Gemini...',
            'current_step': 0,
            'total_steps': total_selected
        })
        job.save_meta()

        # ── Processamento paralelo ────────────────────────────────────────────
        # Chave do dict = page_idx (número real da página no PDF, base 0)
        # Isso garante que page 255 sempre mapeia para o resultado de page 255,
        # independente da ordem em que o Gemini responde.
        results = {}   # {page_idx: period_dict | None}
        completed_count = 0

        with ThreadPoolExecutor(max_workers=min(MAX_GEMINI_WORKERS, total_selected)) as executor:
            # Mapeia future → page_idx para saber qual página cada future representa
            futures = {
                executor.submit(
                    _gemini_extract_period,
                    pdf_path,
                    page_idx,
                    page_idx + 1      # page_number legível para logs
                ): page_idx
                for page_idx in indices
            }

            for future in as_completed(futures):
                page_idx = futures[future]   # garante mapeamento correto
                period   = future.result()
                results[page_idx] = period

                completed_count += 1
                conf_tag = ''
                if period:
                    conf_tag = '' if period.get('confidence') == 'high' else '  ⚠ low confidence'
                    LOG(f"pág {page_idx + 1}",
                        f"{period['start_date']} → {period['end_date']}{conf_tag}")
                else:
                    LOG(f"pág {page_idx + 1}", "sem período identificado", 'WARN')

                job.meta.update({
                    'message': f'Gemini processou {completed_count}/{total_selected} páginas...',
                    'current_step': completed_count
                })
                job.save_meta()

        # ── Monta resultado final em ordem de page_idx ────────────────────────
        # sorted(indices) garante que a lista final está na mesma ordem
        # que o usuário selecionou, independente da chegada paralela.
        res = []
        sem_periodo = []
        low_conf    = []

        for page_idx in sorted(indices):
            period = results.get(page_idx)
            if period is None:
                sem_periodo.append(page_idx + 1)
            elif period.get('confidence') == 'low':
                low_conf.append(page_idx + 1)

            res.append({
                'page_number': page_idx + 1,
                'page_index':  page_idx,
                'period':      period
            })

        t_total = round(time.time() - t_inicio, 1)
        LOG_SEP('RESULTADO')
        LOG('páginas com período',    f"{total_selected - len(sem_periodo)} de {total_selected}")
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

        # ── informações do PDF ────────────────────────────────────────────────
        pdf_size_mb    = round(os.path.getsize(pdf_path) / (1024 * 1024), 1)
        pdf_nome       = job.meta.get('original_filename', os.path.basename(pdf_path))
        reader_info    = PdfReader(pdf_path)
        pdf_total_pags = len(reader_info.pages)
        worker_pid     = os.getpid()
        modelo_desc    = '6 — com data (geral_ai)' if model_type == '6' else '7 — sem data (geral)'
        rpm_uso_agora  = _get_rpm_usage()
        slots_livres   = DOCAI_RPM_LIMIT - rpm_uso_agora

        LOG_SEP('JOB INICIADO')
        LOG('job_id',             job.id)
        LOG('usuário',            user_id)
        LOG('worker PID',         str(worker_pid))
        LOG('modelo',             modelo_desc)
        LOG('arquivo',            pdf_nome)
        LOG('tamanho do pdf',     f"{pdf_size_mb} MB")
        LOG('total págs pdf',     f"{pdf_total_pags} páginas")
        LOG('range selecionado',  f"{len(valid_pages)} páginas recebidas do frontend")
        LOG_SEP('Limite DocAI')
        LOG('limite configurado', f"{DOCAI_RPM_LIMIT} req/min  (margem segura — cota Google: 120)")
        LOG('uso global agora',
            f"{rpm_uso_agora} / {DOCAI_RPM_LIMIT} req no último minuto"
            + ("  ⚠ próximo do limite" if rpm_uso_agora >= DOCAI_RPM_LIMIT * 0.8 else ""))
        LOG('slots disponíveis',
            f"{slots_livres} livres  — "
            + ("sem espera prevista" if slots_livres >= len(valid_pages)
               else f"pode aguardar: {len(valid_pages)} necessários, {slots_livres} livres agora"))

        # ── 1. Validação e ordenação cronológica ──────────────────────────────
        LOG_SEP('Períodos digitados pelo usuário')

        pages_validas   = []
        pages_ignoradas = []

        for p in valid_pages:
            pnum = p.get('page_number', '?')
            try:
                start_dt = datetime.strptime(p['period']['start_date'], '%d/%m/%Y')
                end_dt   = datetime.strptime(p['period']['end_date'],   '%d/%m/%Y')
                if end_dt < start_dt:
                    motivo = (f"end_date '{p['period']['end_date']}' < start_date "
                              f"'{p['period']['start_date']}' — ano provavelmente errado")
                    LOG(f"pág {pnum}",
                        f"{p['period']['start_date']} → {p['period']['end_date']}  "
                        f"IGNORADA: {motivo}", 'WARN')
                    pages_ignoradas.append((pnum, motivo))
                    continue
                dias = len(pd.date_range(start=start_dt, end=end_dt, freq='D'))
                LOG(f"pág {pnum}",
                    f"{p['period']['start_date']} → {p['period']['end_date']}  ({dias} dias)")
                p['start_dt'] = start_dt
                p['end_dt']   = end_dt
                pages_validas.append(p)
            except ValueError as ve:
                motivo = f"data inválida: {ve}"
                LOG(f"pág {pnum}", f"IGNORADA: {motivo}", 'WARN')
                pages_ignoradas.append((pnum, motivo))

        LOG('páginas válidas', f"{len(pages_validas)} de {len(valid_pages)}")

        if not pages_validas:
            raise ValueError("Nenhuma página com período válido após validação.")

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

        # ── 3. Document AI paralelo ───────────────────────────────────────────
        LOG_SEP('Document AI')
        LOG('requisições a enviar',
            f"{len(pages_validas)} páginas  "
            f"(max_workers={min(MAX_DOCAI_WORKERS, len(pages_validas))})")

        t_docai_inicio = time.time()
        results_by_order, total_waited = extractor.process_pdf_parallel(
            pdf_path, pages_validas, job.id
        )
        t_docai_seg = round(time.time() - t_docai_inicio, 1)

        LOG('tempo de resposta DocAI', f"{t_docai_seg}s")
        if total_waited > 0:
            LOG('aguardou rate limit',
                f"{total_waited}s no total  "
                f"(slots ocupados por outros jobs simultâneos)", 'WARN')
        else:
            LOG('espera por rate limit', 'nenhuma — limite não atingido')

        rpm_uso_apos = _get_rpm_usage()
        LOG('uso global após envio',
            f"{rpm_uso_apos} / {DOCAI_RPM_LIMIT} req no último minuto")

        ent_por_pag_partes  = []
        paginas_sem_retorno = []
        for order in sorted(results_by_order.keys()):
            entities_pag, _ = results_by_order[order]
            n    = len(entities_pag)
            pnum = pages_validas[order]['page_number']
            ent_por_pag_partes.append(f"pág {pnum}: {n}")
            if n == 0:
                paginas_sem_retorno.append(pnum)

        LOG('entidades por página', ' · '.join(ent_por_pag_partes))
        if paginas_sem_retorno:
            LOG('págs sem retorno',
                f"{paginas_sem_retorno} — em branco ou formato não reconhecido",
                'WARN')

        # ── 4. Preenchimento do CSV ───────────────────────────────────────────
        # Processamento por página, em ordem cronológica.
        # Para cada página:
        #   - Entidades já chegam ordenadas por Y (feito no _process_single_page)
        #   - Mantemos um ponteiro page_row_ptr para a linha física esperada
        #   - Quando a data está borrada/ausente, inferimos pela posição Y
        #   - Quando a data já está preenchida no master_df, verificamos se é
        #     continuação (slots vazios → mescla) ou duplicata real (tudo cheio → skip)
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

        for page_idx, p_info in enumerate(pages_validas):
            entities_pag, _ = results_by_order.get(page_idx, ([], ""))

            # Sequência de datas do período desta página — base do tracker Y
            page_dr    = pd.date_range(start=p_info['start_dt'], end=p_info['end_dt'], freq='D')
            page_dates = [d.strftime('%d/%m/%Y') for d in page_dr]
            default_year = p_info['start_dt'].year

            # Ponteiro para a linha física esperada dentro do período desta página
            page_row_ptr = 0

            for entity in entities_pag:
                # entities_pag já está ordenada por Y (spatial_sort aplicado no _process_single_page)

                shard_text = getattr(entity, '_shard_text', '')
                data = {
                    prop.type_.lower(): get_text_safely(prop, shard_text)
                    for prop in entity.properties
                }

                raw_dia = data.get('dia', data.get('data', ''))

                # ── Resolução de data em 4 etapas ────────────────────────────

                target_date = None

                # Etapa 1: data completa DD/MM/YYYY no campo (PontoMais, etc.)
                full_date = extract_full_date(raw_dia)
                if full_date and full_date in date_to_row:
                    target_date = full_date
                    full_date_hits += 1
                    # Avança o ponteiro Y até esta data dentro do período da página
                    if full_date in page_dates:
                        new_ptr = page_dates.index(full_date)
                        if new_ptr >= page_row_ptr:
                            page_row_ptr = new_ptr + 1

                # Etapa 2: DD/MM sem ano → usa o ano do período da página (Murici, etc.)
                if target_date is None and raw_dia:
                    match_dm = re.match(r'^(\d{1,2})[/.-](\d{1,2})$', str(raw_dia).strip())
                    if match_dm:
                        d, m = match_dm.groups()
                        years_range = list(range(p_info['start_dt'].year,
                                                  p_info['end_dt'].year + 1))
                        for year in years_range:
                            candidate = f"{d.zfill(2)}/{m.zfill(2)}/{year}"
                            if candidate in date_to_row:
                                target_date = candidate
                                day_month_hits += 1
                                if candidate in page_dates:
                                    new_ptr = page_dates.index(candidate)
                                    if new_ptr >= page_row_ptr:
                                        page_row_ptr = new_ptr + 1
                                break

                # Etapa 3: data borrada/ausente → inferência por posição Y
                # Usa page_row_ptr para saber qual dia esperamos nesta linha física
                if target_date is None:
                    if page_row_ptr < len(page_dates):
                        expected_date = page_dates[page_row_ptr]

                        # Tenta ainda corrigir dígito parcial se raw_dia não está vazio
                        inferred = infer_date_by_position(raw_dia or None, expected_date, default_year)

                        if inferred in date_to_row:
                            target_date = inferred
                            inferidas_por_y += 1
                            page_row_ptr += 1
                            if raw_dia:
                                LOG(f"  inferência Y pág {p_info['page_number']}",
                                    f"DocAI leu '{raw_dia}' → corrigido para '{inferred}'", 'WARN')
                            else:
                                LOG(f"  inferência Y pág {p_info['page_number']}",
                                    f"data ausente → inferida '{inferred}' por posição", 'WARN')

                # Etapa 4: fallback — só o número do dia dentro do período da página
                if target_date is None and raw_dia:
                    raw_clean = re.sub(r'[^\d]', '', str(raw_dia).split('/')[0])
                    if raw_clean:
                        n = int(raw_clean)
                        if 1 <= n <= 31:
                            day_str   = f"{n:02d}"
                            day_match = next(
                                (d for d in page_dates if d.startswith(day_str + '/')),
                                None
                            )
                            if day_match and day_match in date_to_row:
                                idx_cand = date_to_row[day_match]
                                if master_df.at[idx_cand, 'Entrada1'] == "0":
                                    target_date = day_match
                                    fallback_day_hits += 1
                                    if day_match in page_dates:
                                        new_ptr = page_dates.index(day_match)
                                        if new_ptr >= page_row_ptr:
                                            page_row_ptr = new_ptr + 1

                # ── Sem data após todas as etapas ────────────────────────────
                if target_date is None:
                    skip_no_date += 1
                    page_row_ptr += 1  # avança mesmo sem data para não desalinhar
                    continue

                target_idx = date_to_row.get(target_date)
                if target_idx is None:
                    skip_no_row += 1
                    continue

                # ── Preenchimento ou mescla ───────────────────────────────────
                if master_df.at[target_idx, 'Entrada1'] == "0":
                    # Linha vazia — preenche normalmente
                    preencheu = _fill_slots(master_df, target_idx, data)
                    if preencheu:
                        filled_count += 1
                else:
                    # Linha já tem dados — três possibilidades:
                    # 1. Período duplicado (duas páginas com mesmo período) → skip
                    # 2. Página dividida (continuação real com valores novos) → mescla
                    # 3. Todos os slots cheios → skip
                    if _is_duplicate_values(master_df, target_idx, data):
                        # Todos os valores da entidade já existem na linha
                        # → período duplicado ou virada simples → ignora
                        skip_duplicado += 1
                    elif _has_empty_slots(master_df, target_idx):
                        # Há slots vazios E há valores novos → continuação real
                        preencheu = _fill_slots(master_df, target_idx, data)
                        if preencheu:
                            continuacoes_mescladas += 1
                            LOG(f"  mescla pág {p_info['page_number']}",
                                f"continuação mesclada em '{target_date}' "
                                f"(marcações de página dividida)")
                    else:
                        # Slots cheios com valores diferentes — situação inesperada
                        skip_duplicado += 1
        # ── 5. Salvar CSV ─────────────────────────────────────────────────────
        random_id      = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        final_filename = f"Ponto_Extraido_{random_id}.csv"
        out_path       = os.path.join(tempfile.gettempdir(), f"{job.id}.csv")
        master_df.to_csv(out_path, index=False, sep=';', encoding='utf-8-sig')
        csv_size_kb = round(os.path.getsize(out_path) / 1024, 1)

        # ── LOG: resultado ────────────────────────────────────────────────────
        dias_preenchidos = int((master_df['Entrada1'] != "0").sum())
        taxa       = round((dias_preenchidos / len(master_df)) * 100, 1) if len(master_df) > 0 else 0
        taxa_aviso = taxa < 30 and dias_preenchidos > 0

        LOG_SEP('Resultado do preenchimento')
        LOG('dias preenchidos',
            f"{dias_preenchidos} / {len(master_df)}  (taxa: {taxa}%)"
            + ("  ⚠ ABAIXO DO LIMIAR (30%)" if taxa_aviso else ""))
        LOG('resolução data completa',
            f"{full_date_hits}  (DD/MM/YYYY direto do DocAI)")
        LOG('resolução DD/MM + ano página',
            f"{day_month_hits}  (ano inferido do período digitado)")
        LOG('inferidas por posição Y',
            f"{inferidas_por_y}  (data borrada/ausente recuperada por ordem física)")
        LOG('resolução fallback dia',
            f"{fallback_day_hits}  (número do dia apenas)")
        LOG('continuações mescladas',
            f"{continuacoes_mescladas}  (marcações de página dividida unificadas)")
        LOG('duplicados ignorados',
            f"{skip_duplicado}  (virada de página simples — linha idêntica)")
        LOG('skip fora do range',    str(skip_no_row))
        LOG('skip sem data',         str(skip_no_date))

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

        job.meta.update({
            'status':    'completed',
            'file_path': out_path,
            'filename':  final_filename
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
