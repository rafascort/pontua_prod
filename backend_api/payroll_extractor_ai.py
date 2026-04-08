# /opt/pontua/AutoPonto/backend_api/payroll_extractor_ai.py
#
# CORREÇÕES aplicadas:
#   1. Logs reorganizados no padrão LOG/LOG_SEP do extractor_geral_ai.py
#   2. process_payroll_task define job.meta['pages_to_process'] = total
#   3. process_payroll_final_task repassa user_email para process_payroll_task

import os
import tempfile
import pandas as pd
import json
import re
import time
import traceback
import unicodedata
from datetime import datetime
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
# ─────────────────────────────────────────────────────────────────────────────


class PayrollExtractorAI:
    def __init__(self, job=None):
        self.job    = job
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model_id = "gemini-2.5-flash"

    # ── Processa uma página individual via Gemini ─────────────────────────────
    def _process_single_page(self, pdf_path, p_num, prompt_type, targets=None):
        tmp_path = None
        try:
            reader = PdfReader(pdf_path)
            writer = PdfWriter()
            writer.add_page(reader.pages[p_num - 1])

            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                writer.write(tmp.name)
                tmp_path = tmp.name

            uploaded = self.client.files.upload(file=tmp_path)
            file     = self.client.files.get(name=uploaded.name)
            while file.state.name == "PROCESSING":
                time.sleep(1)
                file = self.client.files.get(name=uploaded.name)

            if prompt_type == "analyze":
                prompt = """Analise o HOLERITE. Ignore o Cartão Ponto.
1. Extraia o NOME DO FUNCIONÁRIO (ignore empresa).
2. Liste VERBAS e CAMPOS DE RODAPÉ na ordem de cima para baixo.

REGRAS CRÍTICAS:
- NÃO CRIE DUPLICADOS. Itens com apenas diferença de espaços ou pontos são o mesmo item.
- Exemplo: 'SALÁRIO CONTR.INSS' e 'SALÁRIO CONTR. INSS' → listar UMA VEZ.
- Não confunda 'Horas Normais' com 'Horas Normais Noturnas'.
JSON: {"nomes": [], "itens": []}"""
            else:
                prompt = f"""Ignore o Cartão Ponto. No Holerite, extraia os dados com precisão:
JSON: {{"nome": "Nome", "periodo": "MM/AAAA", "dados": [{{"campo": "Item", "ref": "Ref", "valor": "Valor"}}]}}

DIFERENCIAÇÃO OBRIGATÓRIA:
- 'Horas Normais' é um item. 'Horas Normais Noturnas' é OUTRO item. Não troque os valores.
Extraia apenas: {targets}"""

            response = self.client.models.generate_content(
                model=self.model_id, contents=[file, prompt]
            )
            self.client.files.delete(name=file.name)
            return json.loads(re.search(r'\{.*\}', response.text, re.DOTALL).group())

        except Exception as e:
            LOG(f'erro página {p_num}', str(e), 'ERR ')
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try: os.unlink(tmp_path)
                except: pass

    # ── ETAPA 1: Identificação de verbas ─────────────────────────────────────
    def scan_verbas_task(self, pdf_path, pages_range):
        reader    = PdfReader(pdf_path)
        pages     = self._parse_range(pages_range, len(reader.pages))
        total     = len(pages)
        t_inicio  = time.time()
        worker_pid = os.getpid()

        LOG_SEP('HOLERITE — ANÁLISE INICIADA')
        LOG('job_id',          self.job.id if self.job else '?')
        LOG('worker PID',      str(worker_pid))
        LOG('páginas',         f"{total}  ({pages_range})")
        LOG('total no PDF',    f"{len(reader.pages)} páginas")
        LOG_SEP()

        if self.job:
            self.job.meta.update({
                'total_steps': total, 'current_step': 0,
                'status': 'processing', 'message': 'Identificando verbas...',
            })
            self.job.save_meta()

        unique_items_ordered = {}
        all_nomes            = set()
        results_by_page      = {}
        erros                = []

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures        = {executor.submit(self._process_single_page, pdf_path, p, "analyze"): p for p in pages}
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
                if is_valid_name(n): all_nomes.add(str(n).strip().upper())

        t_total = round(time.time() - t_inicio, 1)

        LOG_SEP('ANÁLISE CONCLUÍDA')
        LOG('tempo',           f"{t_total}s")
        LOG('verbas únicas',   str(len(unique_items_ordered)))
        LOG('funcionários',    str(len(all_nomes)))
        if erros:
            LOG('páginas sem retorno', str(erros), 'WARN')
        LOG_SEP()

        result = {
            "nomes":    sorted(list(all_nomes)),
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
        reader    = PdfReader(pdf_path)
        pages     = self._parse_range(pages_range, len(reader.pages))
        total     = len(pages)
        t_inicio  = time.time()
        worker_pid = os.getpid()

        LOG_SEP('HOLERITE — EXTRAÇÃO INICIADA')
        LOG('job_id',          job.id)
        LOG('usuário',         user_email or '?')
        LOG('worker PID',      str(worker_pid))
        LOG('páginas',         f"{total}  ({pages_range})")
        LOG('verbas selecionadas', str(len(selected_verbas)))
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

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(self._process_single_page, pdf_path, p, "process", clean_targets): p
                for p in pages
            }
            for future in as_completed(futures):
                p_num = futures[future]
                data  = future.result()
                if data:
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
        abas    = 0
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for nome, group in df_full.groupby('Nome'):
                meses = sorted(
                    group['Mês'].unique(),
                    key=lambda x: pd.to_datetime(x, format='%m/%Y', errors='coerce')
                )
                df_aba           = pd.DataFrame(index=meses, columns=multi_col).fillna('0')
                df_aba.index.name = 'Mês'

                for _, row in group.iterrows():
                    c_norm = super_norm(row['Campo'])
                    target = next((t for t in sorted_targets if super_norm(t) == c_norm), None)
                    if target:
                        df_aba.at[row['Mês'], (target, 'Ref.')]   = row['Ref']
                        df_aba.at[row['Mês'], (target, 'Valor')]  = row['Valor']

                sheet_name = re.sub(r'[^a-zA-Z0-9 ]', '', str(nome))[:31]
                df_aba.to_excel(writer, sheet_name=sheet_name, index=True)
                abas += 1

        t_total  = round(time.time() - t_inicio, 1)
        xlsx_kb  = round(os.path.getsize(output_path) / 1024, 1)

        LOG_SEP('EXTRAÇÃO CONCLUÍDA')
        LOG('tempo',           f"{t_total}s")
        LOG('funcionários',    f"{abas} aba(s) gerada(s)")
        LOG('arquivo',         f"Folha_{job.id}.xlsx  ({xlsx_kb} KB)")
        if erros:
            LOG('páginas sem retorno', str(erros), 'WARN')
        LOG_SEP()

        # ── CORREÇÃO: pages_to_process para /api/download contabilizar ────────
        job.meta.update({
            'status':           'completed',
            'file_path':        output_path,
            'pages_to_process': total,
        })
        job.save_meta()
        return True

    # ── Helper de parse de range ──────────────────────────────────────────────
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
