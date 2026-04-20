# /opt/pontua/AutoPonto/backend_api/payroll_extractor_ai.py
#
# OTIMIZAÇÕES v2:
#   1. Inline base64 em vez de Files API (elimina upload + polling)
#   2. Pré-split de páginas antes do paralelismo (PdfReader 1× em vez de N×)
#   3. max_workers aumentado para 20
#   4. Logs com tabelas completas: verbas selecionadas, funcionários detectados
#   5. Abas geradas com nomes dos funcionários no log final
#
# CORREÇÕES v3:
#   6. Suporte a múltiplos holerites por página do PDF
#   7. Preenchimento de meses faltantes com valores zerados
#
# Mantido do original:
#   - Processamento página a página (garante precisão)
#   - Retry automático (até 3 tentativas)
#   - safe_parse_json() — parse robusto de JSON
#   - normalize_name_key() — agrupa nomes com typos de OCR
#   - Mapeamento future → p_num (garante ordem correta)

import os
import base64
import tempfile
import pandas as pd
import json
import re
import time
import traceback
import unicodedata
from io import BytesIO
from datetime import datetime
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from rq import get_current_job
from pypdf import PdfReader, PdfWriter

# ── Suprime logs ruidosos de bibliotecas externas ────────────────────────────
import logging
logging.basicConfig(level=logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google_genai.models").setLevel(logging.WARNING)
# ─────────────────────────────────────────────────────────────────────────────

# ── Configuração ─────────────────────────────────────────────────────────────
MAX_GEMINI_WORKERS = 20
# ─────────────────────────────────────────────────────────────────────────────


# ─── LOG CENTRAL (mesmo padrão do extractor_geral_ai) ────────────────────────
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


def LOG_TABLE(title, items):
    """Imprime uma tabela formatada no log com título e itens numerados."""
    if not items:
        return
    col_width = 57
    print(f"[LOG ] ┌─────────────────────────────────────────────────────────────────────┐", flush=True)
    print(f"[LOG ] │  {title:<67} │", flush=True)
    print(f"[LOG ] ├───────┬─────────────────────────────────────────────────────────────┤", flush=True)
    for i, item in enumerate(items, 1):
        item_str = str(item)[:col_width]
        print(f"[LOG ] │ {i:>4}  │ {item_str:<{col_width}} │", flush=True)
    print(f"[LOG ] └───────┴─────────────────────────────────────────────────────────────┘", flush=True)
# ─────────────────────────────────────────────────────────────────────────────


# ─── UTILITÁRIOS ─────────────────────────────────────────────────────────────
def super_norm(text):
    """Remove acentos, espaços e pontos — comparação rigorosa de verbas."""
    if not text: return ""
    text = "".join(
        c for c in unicodedata.normalize('NFD', str(text).lower())
        if unicodedata.category(c) != 'Mn'
    )
    return re.sub(r'[^a-z0-9]', '', text)

def clean_value(val):
    if isinstance(val, dict):
        return str(next(iter(val.values()))) if val else "0"
    return str(val).strip() if val is not None else "0"

def is_valid_name(name):
    if not name or len(name) < 8: return False
    forbidden = ["LTDA", "CNPJ", "CPF", "RUA", "AVENIDA", "ENDERECO", "EMPRESA", "S.A", "EIRELI"]
    if any(w in name.upper() for w in forbidden): return False
    if len(re.findall(r'\d', name)) > 4: return False
    return True


def safe_parse_json(text):
    """Parse robusto de JSON — lida com objetos, arrays e 'Extra data'."""
    if not text:
        return None

    # ── Tenta array primeiro (para múltiplos holerites por página) ────────
    match_arr = re.search(r'\[.*\]', text, re.DOTALL)
    match_obj = re.search(r'\{.*\}', text, re.DOTALL)

    # Se encontrou array que contém objetos, tenta parsear como array
    if match_arr:
        arr_str = match_arr.group()
        try:
            parsed = json.loads(arr_str)
            if isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict):
                return parsed
        except json.JSONDecodeError:
            # Tenta limpar trailing commas
            cleaned = re.sub(r',\s*}', '}', arr_str)
            cleaned = re.sub(r',\s*]', ']', cleaned)
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict):
                    return parsed
            except json.JSONDecodeError:
                pass

    # ── Fallback: tenta objeto único ──────────────────────────────────────
    if not match_obj:
        return None

    json_str = match_obj.group()

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        # "Extra data" = mais de um objeto JSON concatenado na resposta
        if "Extra data" in str(e):
            # Tenta extrair TODOS os objetos JSON concatenados
            objects = _extract_all_json_objects(json_str)
            if objects:
                return objects if len(objects) > 1 else objects[0]

        # Tenta limpar trailing commas
        cleaned = re.sub(r',\s*}', '}', json_str)
        cleaned = re.sub(r',\s*]', ']', cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    return None


def _extract_all_json_objects(text):
    """Extrai múltiplos objetos JSON concatenados de uma string."""
    objects = []
    i = 0
    while i < len(text):
        if text[i] == '{':
            depth = 0
            in_string = False
            escape_next = False
            for j in range(i, len(text)):
                ch = text[j]
                if escape_next:
                    escape_next = False
                    continue
                if ch == '\\' and in_string:
                    escape_next = True
                    continue
                if ch == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(text[i:j+1])
                            objects.append(obj)
                        except json.JSONDecodeError:
                            pass
                        i = j + 1
                        break
            else:
                break
        else:
            i += 1
    return objects


def normalize_name_key(name):
    """Chave de agrupamento para nomes, tolerando typos de OCR (letras duplicadas)."""
    if not name:
        return ""
    n = super_norm(name)
    # Colapsa letras repetidas consecutivas (ex: 'uiilio' → 'uilio' → mesmo que 'uilio')
    n = re.sub(r'(.)\1+', r'\1', n)
    return n
# ─────────────────────────────────────────────────────────────────────────────


def _presplit_pages(pdf_path, pages):
    """
    Abre o PDF UMA vez e extrai cada página como bytes em memória.
    Retorna dict {p_num: bytes_da_pagina_como_pdf}.
    """
    reader = PdfReader(pdf_path)
    total_pdf = len(reader.pages)
    page_buffers = {}

    t0 = time.time()
    for p in pages:
        idx = p - 1
        if 0 <= idx < total_pdf:
            writer = PdfWriter()
            writer.add_page(reader.pages[idx])
            buf = BytesIO()
            writer.write(buf)
            page_buffers[p] = buf.getvalue()

    elapsed = round(time.time() - t0, 2)
    LOG('pré-split', f"{len(page_buffers)} páginas em {elapsed}s")
    return page_buffers, total_pdf


def _generate_full_month_range(meses_list):
    """
    Dado uma lista de meses no formato 'MM/AAAA', gera todos os meses
    entre o primeiro e o último (inclusive), preenchendo lacunas.
    """
    if not meses_list:
        return meses_list

    parsed = []
    for m in meses_list:
        try:
            dt = pd.to_datetime(m, format='%m/%Y')
            parsed.append(dt)
        except:
            pass

    if not parsed:
        return meses_list

    dt_min = min(parsed)
    dt_max = max(parsed)

    full_range = pd.date_range(start=dt_min, end=dt_max, freq='MS')
    return [dt.strftime('%m/%Y') for dt in full_range]


class PayrollExtractorAI:
    # ── Gemini 2.5 Flash — preço USD por 1M tokens ────────────────────────
    PRICE_IN_PER_M  = 0.30   # input
    PRICE_OUT_PER_M = 2.50   # output (inclui thinking)
    USD_TO_BRL      = 5.70   # taxa aproximada apenas para display

    def __init__(self, job=None):
        self.job    = job
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model_id = "gemini-2.5-flash"

        # Acumuladores de tokens (thread-safe)
        self._token_in   = 0
        self._token_out  = 0
        self._token_lock = Lock()

    # ── Rastreia uso de tokens da resposta Gemini ────────────────────────
    def _track_usage(self, response):
        try:
            meta = response.usage_metadata
            p_in      = getattr(meta, 'prompt_token_count', 0) or 0
            p_out     = getattr(meta, 'candidates_token_count', 0) or 0
            p_thought = getattr(meta, 'thoughts_token_count', 0) or 0
            with self._token_lock:
                self._token_in  += p_in
                self._token_out += p_out + p_thought
        except Exception:
            pass

    # ── Log de custo em UMA linha ────────────────────────────────────────
    def _log_cost(self):
        cost_in   = (self._token_in  / 1_000_000) * self.PRICE_IN_PER_M
        cost_out  = (self._token_out / 1_000_000) * self.PRICE_OUT_PER_M
        total_usd = cost_in + cost_out
        total_brl = total_usd * self.USD_TO_BRL
        LOG('custo Gemini',
            f"{self._token_in:,} in + {self._token_out:,} out = ${total_usd:.4f}  (~R$ {total_brl:.4f})")

    # ── Processa uma página via Gemini usando inline base64 (com retry) ──────
    def _process_single_page(self, page_bytes, p_num, prompt_type, targets=None):
        MAX_RETRIES = 2
        last_error = None

        # Codifica base64 uma vez (fora do retry)
        page_b64 = base64.standard_b64encode(page_bytes).decode('utf-8')

        for attempt in range(MAX_RETRIES + 1):
            try:
                if prompt_type == "analyze":
                    prompt = """Analise TODOS os HOLERITES desta página. Ignore o Cartão Ponto.
Uma página pode conter MAIS DE UM holerite (contracheque). Analise TODOS eles.

1. Extraia o NOME DO FUNCIONÁRIO de cada holerite (ignore empresa).
2. Liste TODAS as VERBAS e CAMPOS DE RODAPÉ de todos os holerites, na ordem de cima para baixo.

REGRAS CRÍTICAS:
- NÃO CRIE DUPLICADOS. Itens com apenas diferença de espaços ou pontos são o mesmo item.
- Exemplo: 'SALÁRIO CONTR.INSS' e 'SALÁRIO CONTR. INSS' → listar UMA VEZ.
- Não confunda 'Horas Normais' com 'Horas Normais Noturnas'.
JSON: {"nomes": [], "itens": []}"""
                else:
                    prompt = f"""Ignore o Cartão Ponto. Esta página pode conter MAIS DE UM holerite (contracheque).
Extraia os dados de CADA holerite separadamente com precisão.

Se houver APENAS UM holerite na página, retorne UM objeto JSON.
Se houver DOIS OU MAIS holerites na página, retorne um ARRAY JSON com um objeto por holerite.

Formato para UM holerite:
{{"nome": "Nome", "periodo": "MM/AAAA", "dados": [{{"campo": "Item", "ref": "Ref", "valor": "Valor"}}]}}

Formato para MÚLTIPLOS holerites:
[{{"nome": "Nome", "periodo": "MM/AAAA", "dados": [{{"campo": "Item", "ref": "Ref", "valor": "Valor"}}]}}, {{"nome": "Nome", "periodo": "MM/AAAA", "dados": [...]}}]

DIFERENCIAÇÃO OBRIGATÓRIA:
- 'Horas Normais' é um item. 'Horas Normais Noturnas' é OUTRO item. Não troque os valores.
- Cada holerite tem seu próprio período (Competência MM/AAAA). Extraia CADA UM separadamente.
Extraia apenas: {targets}"""

                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=[
                        {
                            "inline_data": {
                                "mime_type": "application/pdf",
                                "data": page_b64
                            }
                        },
                        prompt
                    ]
                )

                # Rastreia tokens consumidos nesta chamada
                self._track_usage(response)

                result = safe_parse_json(response.text)
                if result:
                    return result

                last_error = f"JSON inválido (tentativa {attempt+1}/{MAX_RETRIES+1})"
                LOG(f'página {p_num}', last_error, 'WARN')
                if attempt < MAX_RETRIES:
                    time.sleep(2)
                    continue

            except Exception as e:
                last_error = str(e)
                if attempt < MAX_RETRIES:
                    LOG(f'página {p_num}', f"erro tentativa {attempt+1}: {e} — retentando...", 'WARN')
                    time.sleep(2)
                    continue

        LOG(f'erro página {p_num}', f"falhou após {MAX_RETRIES+1} tentativas: {last_error}", 'ERR ')
        return None

    # ── ETAPA 1: Identificação de verbas ─────────────────────────────────────
    def scan_verbas_task(self, pdf_path, pages_range):
        pages     = self._parse_range_from_file(pdf_path, pages_range)
        total     = len(pages)
        t_inicio  = time.time()
        worker_pid = os.getpid()

        # Pré-split: abre o PDF 1 vez, extrai bytes de cada página
        page_buffers, total_pdf = _presplit_pages(pdf_path, pages)

        LOG_SEP('HOLERITE — ANÁLISE INICIADA')
        LOG('job_id',          self.job.id if self.job else '?')
        LOG('worker PID',      str(worker_pid))
        LOG('páginas',         f"{total}  ({pages_range})")
        LOG('total no PDF',    f"{total_pdf} páginas")
        LOG_SEP()

        if self.job:
            self.job.meta.update({
                'total_steps': total, 'current_step': 0,
                'status': 'processing', 'message': 'Identificando verbas...',
            })
            self.job.save_meta()

        unique_items_ordered = {}
        all_nomes            = {}   # dict {chave_normalizada: nome_original}
        results_by_page      = {}
        erros                = []

        with ThreadPoolExecutor(max_workers=min(MAX_GEMINI_WORKERS, total)) as executor:
            futures = {
                executor.submit(self._process_single_page, page_buffers[p], p, "analyze"): p
                for p in pages if p in page_buffers
            }
            completed_count = 0

            for future in as_completed(futures):
                p_num = futures[future]
                data  = future.result()
                if data:
                    results_by_page[p_num] = data
                    LOG(f'página {p_num}', f"ok — {len(data.get('itens', []))} itens, {len(data.get('nomes', []))} nomes")
                else:
                    erros.append(p_num)
                    LOG(f'página {p_num}', 'sem retorno', 'WARN')

                completed_count += 1
                if self.job:
                    self.job.meta.update({
                        'current_step': completed_count,
                        'message':      f"Analisando página {p_num}...",
                    })
                    self.job.save_meta()

        for p_num in sorted(results_by_page.keys()):
            data = results_by_page[p_num]
            for item in data.get('itens', []):
                clean = str(item).strip()
                if '{' not in clean and len(clean) > 2 and not re.match(r'^[0-9\.,\-/%\s:]+$', clean):
                    norm_key = super_norm(clean)
                    if norm_key not in unique_items_ordered:
                        unique_items_ordered[norm_key] = clean
            for n in data.get('nomes', []):
                if is_valid_name(n):
                    name_upper = str(n).strip().upper()
                    name_key = normalize_name_key(name_upper)
                    if name_key not in all_nomes:
                        all_nomes[name_key] = name_upper

        t_total = round(time.time() - t_inicio, 1)

        LOG_SEP('ANÁLISE CONCLUÍDA')
        LOG('tempo',           f"{t_total}s")
        LOG('verbas únicas',   str(len(unique_items_ordered)))
        if erros:
            LOG('páginas sem retorno', str(erros), 'WARN')
        LOG_TABLE(f"FUNCIONÁRIOS DETECTADOS ({len(all_nomes)})", sorted(list(all_nomes.values())))
        self._log_cost()
        LOG_SEP()

        result = {
            "nomes":    sorted(list(all_nomes.values())),
            "verbas":   list(unique_items_ordered.values()),
            "pdf_path": pdf_path,
            "pages":    pages_range,
        }
        if self.job:
            self.job.meta.update({'status': 'completed', 'result': result})
            self.job.save_meta()
        return result

    # ── ETAPA 2: Geração do Excel ─────────────────────────────────────────────
    def process_payroll_task(self, pdf_path, pages_range, selected_verbas, user_email=None):
        job       = get_current_job()
        pages     = self._parse_range_from_file(pdf_path, pages_range)
        total     = len(pages)
        t_inicio  = time.time()
        worker_pid = os.getpid()

        # Pré-split: abre o PDF 1 vez, extrai bytes de cada página
        page_buffers, total_pdf = _presplit_pages(pdf_path, pages)

        LOG_SEP('HOLERITE — EXTRAÇÃO INICIADA')
        LOG('job_id',          job.id)
        LOG('usuário',         user_email or '?')
        LOG('worker PID',      str(worker_pid))
        LOG('páginas',         f"{total}  ({pages_range})")
        LOG_TABLE(f"VERBAS SELECIONADAS ({len(selected_verbas)})", selected_verbas)
        LOG_SEP()

        job.meta.update({
            'total_steps': total, 'current_step': 0,
            'status': 'processing', 'message': 'Extraindo dados...',
        })
        job.save_meta()

        clean_targets  = [str(v).strip() for v in selected_verbas]
        sorted_targets = sorted(clean_targets, key=len, reverse=True)
        col_tuples     = [(t, sub) for t in clean_targets for sub in ['Ref.', 'Valor']]
        multi_col      = pd.MultiIndex.from_tuples(col_tuples)

        all_extracted   = []
        erros           = []
        completed_count = 0

        with ThreadPoolExecutor(max_workers=min(MAX_GEMINI_WORKERS, total)) as executor:
            futures = {
                executor.submit(self._process_single_page, page_buffers[p], p, "process", clean_targets): p
                for p in pages if p in page_buffers
            }
            for future in as_completed(futures):
                p_num = futures[future]
                data  = future.result()
                if data:
                    # ── CORREÇÃO v3: suporte a múltiplos holerites por página ─
                    if isinstance(data, list):
                        # Gemini retornou array — múltiplos holerites na página
                        all_extracted.extend(data)
                        total_campos = sum(len(d.get('dados', [])) for d in data)
                        LOG(f'página {p_num}', f"ok — {len(data)} holerites, {total_campos} campos")
                    else:
                        # Gemini retornou objeto único — um holerite na página
                        all_extracted.append(data)
                        LOG(f'página {p_num}', f"ok — {len(data.get('dados', []))} campos")
                else:
                    erros.append(p_num)
                    LOG(f'página {p_num}', 'sem retorno', 'WARN')

                completed_count += 1
                job.meta.update({
                    'current_step': completed_count,
                    'message':      f"Extraindo página {p_num}...",
                })
                job.save_meta()

        if not all_extracted:
            LOG('resultado', 'nenhum dado extraído — abortando', 'ERR ')
            job.meta.update({'status': 'error', 'error': 'Nenhum dado extraído das páginas.'})
            job.save_meta()
            return False

        # ── Monta Excel ───────────────────────────────────────────────────────
        output_path = os.path.join(tempfile.gettempdir(), f"Folha_{job.id}.xlsx")
        temp_data   = []
        for e in all_extracted:
            nome, mes = clean_value(e.get('nome')), clean_value(e.get('periodo'))
            for item in e.get('dados', []):
                temp_data.append({
                    'Nome':  nome,
                    'Mês':   mes,
                    'Campo': clean_value(item.get('campo')),
                    'Ref':   clean_value(item.get('ref')),
                    'Valor': clean_value(item.get('valor')),
                })

        df_full = pd.DataFrame(temp_data)

        # Normalizar nomes para agrupar variações de OCR na mesma aba
        df_full['Nome_key'] = df_full['Nome'].apply(normalize_name_key)

        # Mapeia cada chave normalizada ao primeiro nome encontrado
        name_map = {}
        for _, row in df_full.iterrows():
            k = row['Nome_key']
            if k not in name_map:
                name_map[k] = row['Nome']

        abas = 0
        nomes_abas = []   # lista de nomes dos funcionários (para log final)

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for nome_key, group in df_full.groupby('Nome_key'):
                nome_display = name_map.get(nome_key, nome_key)

                # ── CORREÇÃO v3: gerar range completo de meses ────────────
                meses_existentes = sorted(
                    group['Mês'].unique(),
                    key=lambda x: pd.to_datetime(x, format='%m/%Y', errors='coerce')
                )
                meses = _generate_full_month_range(meses_existentes)
                # ──────────────────────────────────────────────────────────

                df_aba           = pd.DataFrame(index=meses, columns=multi_col).fillna('0')
                df_aba.index.name = 'Mês'

                for _, row in group.iterrows():
                    c_norm = super_norm(row['Campo'])
                    target = next((t for t in sorted_targets if super_norm(t) == c_norm), None)
                    if target:
                        df_aba.at[row['Mês'], (target, 'Ref.')] = row['Ref']
                        df_aba.at[row['Mês'], (target, 'Valor')] = row['Valor']

                sheet_name = re.sub(r'[^a-zA-Z0-9 ]', '', str(nome_display))[:31]
                df_aba.to_excel(writer, sheet_name=sheet_name, index=True)
                abas += 1
                nomes_abas.append(nome_display)

        t_total  = round(time.time() - t_inicio, 1)
        xlsx_kb  = round(os.path.getsize(output_path) / 1024, 1)

        LOG_SEP('EXTRAÇÃO CONCLUÍDA')
        LOG('tempo',           f"{t_total}s")
        LOG('arquivo',         f"Folha_{job.id}.xlsx  ({xlsx_kb} KB)")
        if erros:
            LOG('páginas sem retorno', str(erros), 'WARN')
        LOG_TABLE(f"ABAS GERADAS — {abas} FUNCIONÁRIO(S)", nomes_abas)
        self._log_cost()
        LOG_SEP()

        # pages_to_process para /api/download contabilizar
        job.meta.update({
            'status':           'completed',
            'file_path':        output_path,
            'pages_to_process': total,
        })
        job.save_meta()
        return True

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _parse_range_from_file(self, pdf_path, pages_str):
        """Parse de range com leitura do total de páginas do PDF."""
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        return self._parse_range(pages_str, total_pages)

    def _parse_range(self, pages_str, total_pages):
        res = []
        for part in str(pages_str).split(','):
            part = part.strip()
            if '-' in part:
                try:
                    s, e = map(int, part.split('-'))
                    res.extend(range(s, min(e, total_pages) + 1))
                except: pass
            elif part.isdigit():
                p = int(part)
                if p <= total_pages: res.append(p)
        return sorted(list(set(p for p in res if p > 0)))


# ── Funções de entrada para o worker RQ ──────────────────────────────────────

def scan_verbas_task(pdf_path, pages, user_id):
    return PayrollExtractorAI(job=get_current_job()).scan_verbas_task(pdf_path, pages)

def process_payroll_final_task(pdf_path, pages, selected_verbas, user_id):
    return PayrollExtractorAI(job=get_current_job()).process_payroll_task(
        pdf_path, pages, selected_verbas, user_email=user_id
    )
