# /opt/pontua/AutoPonto/backend_api/payroll_extractor_ai.py
#
# v2.5 — tratamento de páginas sem nome de funcionário:
#
#   OPÇÃO 2 — Carry-forward por ordem de página:
#     - Resultados das páginas são guardados por número de página
#     - Após extração paralela, percorre em ordem crescente de página
#     - Página sem nome herda o último nome válido visto antes dela
#     - Ex: pág 1 "VALMIR SCOTTA", pág 2 sem nome → pág 2 recebe "VALMIR SCOTTA"
#
#   OPÇÃO 3 — Fallback para único nome conhecido:
#     - Se known_names tiver exatamente 1 funcionário e a página não tem nome,
#       atribui diretamente esse nome (sem precisar de carry-forward)
#     - Aplicado antes do carry-forward (mais simples e direto)
#
#   As duas opções são aplicadas em sequência:
#     1. Opção 3 primeiro (se known_names == 1 entrada)
#     2. Opção 2 como fallback (carry-forward do último nome válido)
#     3. known_names[0] como último recurso se ainda sem nome
#
# v2.4:
#   OPÇÃO A — Prompt do scan melhorado (define por EXCLUSÃO o que não é verba)
#   OPÇÃO B — Filtro Python pós-scan (regex + heurísticas)
#   FUZZY GROUPING — nomes com 1-2 letras diferentes vão para a mesma aba
#   FILTRO DE NOMES — descarta registros com nomes inválidos (empresa, cabeçalhos)
#
# Histórico:
#   v2.3: Meses faltantes preenchidos com '0'; suporte a array JSON por página
#   v2.1: Formatação brasileira de números (Ref + Valor)
#   v2:   Inline base64, pré-split de páginas, max_workers=60

import os
import base64
import tempfile
import pandas as pd
import json
import re
import time
import traceback
import unicodedata
from difflib import SequenceMatcher
from io import BytesIO
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
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
MAX_GEMINI_WORKERS = 60
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
# ─────────────────────────────────────────────────────────────────────────────


# ─── FORMATAÇÃO BRASILEIRA DE NÚMEROS ────────────────────────────────────────
def format_br_number(val):
    """
    Formata valor no padrão brasileiro: ponto para milhares, vírgula para decimais.
    Aceita US (1500.40), BR (1.500,40), misto — normaliza tudo.
    Idempotente: "1.500,40" → "1.500,40".
    """
    if val is None:
        return "0"
    s = str(val).strip()
    if not s or s == "0":
        return s if s else "0"

    m = re.match(r'^(-?)([\d.,]+)$', s)
    if not m:
        return s

    negative = bool(m.group(1))
    num_str  = m.group(2)

    last_dot   = num_str.rfind('.')
    last_comma = num_str.rfind(',')

    if last_comma > last_dot:
        integer_part, decimal_part = num_str.rsplit(',', 1)
        integer_part = integer_part.replace('.', '').replace(',', '')
    elif last_dot > last_comma:
        after = num_str[last_dot+1:]
        if len(after) <= 2 and ',' not in num_str:
            integer_part, decimal_part = num_str.rsplit('.', 1)
            integer_part = integer_part.replace('.', '').replace(',', '')
        elif len(after) <= 2 and ',' in num_str:
            integer_part, decimal_part = num_str.rsplit('.', 1)
            integer_part = integer_part.replace(',', '').replace('.', '')
        else:
            integer_part = num_str.replace('.', '').replace(',', '')
            decimal_part = ""
    else:
        integer_part = num_str
        decimal_part = ""

    try:
        int_val = int(integer_part) if integer_part else 0
    except ValueError:
        return s

    formatted_int = f"{int_val:,}".replace(',', '.')

    if decimal_part:
        if len(decimal_part) == 1:
            decimal_part += '0'
        elif len(decimal_part) > 2:
            decimal_part = decimal_part[:2]
        result = f"{formatted_int},{decimal_part}"
    else:
        result = formatted_int

    return ('-' + result) if negative else result
# ─────────────────────────────────────────────────────────────────────────────


def is_valid_name(name):
    """Verifica se uma string parece ser um nome de funcionário válido."""
    if not name or len(name) < 8: return False
    forbidden = ["LTDA", "CNPJ", "CPF", "RUA", "AVENIDA", "ENDERECO", "EMPRESA", "S.A", "EIRELI"]
    if any(w in name.upper() for w in forbidden): return False
    if len(re.findall(r'\d', name)) > 4: return False
    return True


def safe_parse_json(text):
    """Parse robusto de JSON — lida com 'Extra data' e detecta array (múltiplos holerites/página)."""
    if not text:
        return None

    cleaned = text.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    cleaned = cleaned.strip()

    # Tenta array primeiro (múltiplos holerites por página)
    arr_match = _find_balanced(cleaned, '[', ']')
    if arr_match:
        try:
            parsed = json.loads(arr_match)
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                if any('nome' in h or 'periodo' in h for h in parsed if isinstance(h, dict)):
                    return parsed
        except json.JSONDecodeError:
            pass

    # Fallback: objeto único em qualquer posição
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if not match:
        return None

    json_str = match.group()

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        if "Extra data" in str(e):
            depth = 0
            in_string = False
            escape_next = False
            for i, ch in enumerate(json_str):
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
                            return json.loads(json_str[:i+1])
                        except json.JSONDecodeError:
                            break

        fixed = re.sub(r',\s*}', '}', json_str)
        fixed = re.sub(r',\s*]', ']', fixed)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

    return None


def _find_balanced(text, open_ch, close_ch):
    """Encontra o primeiro bloco balanceado completo entre open_ch e close_ch."""
    start = text.find(open_ch)
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        ch = text[i]
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
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    return None


def normalize_name_key(name):
    """Chave de agrupamento para nomes, tolerando typos de OCR (letras duplicadas)."""
    if not name:
        return ""
    n = super_norm(name)
    n = re.sub(r'(.)\1+', r'\1', n)
    return n


# ─── v2.4: FUZZY GROUPING DE NOMES ───────────────────────────────────────────
def fuzzy_group_names(names, threshold=0.82):
    """
    Agrupa nomes com diferença de 1-2 letras ou sobrenome faltando na mesma aba.
    Retorna dict {nome_original → nome_canônico (primeiro encontrado do grupo)}.

    Exemplos que ficam na mesma aba:
      "VALMIR SCOTTA"           + "VALMIR SCOTA"            → mesma (ratio ~0.96)
      "DANILSON DE OLIVEIRA VARGAS" + "DANILSON DE OLIVERA VARGAS" → mesma (ratio ~0.97)
      "JOSE DA SILVA"           + "JOSE SILVA"              → mesma (ratio ~0.87)

    Exemplos que ficam em abas separadas:
      "VALMIR SCOTTA"           + "HOSPITAL MONTENEGRO"     → separadas (ratio ~0.3)
    """
    canonical = []  # lista de (chave_normalizada, nome_display)
    mapping   = {}
    for name in names:
        key     = normalize_name_key(name)
        matched = None
        for canon_key, canon_name in canonical:
            if SequenceMatcher(None, key, canon_key).ratio() >= threshold:
                matched = canon_name
                break
        if matched:
            mapping[name] = matched
        else:
            canonical.append((key, name))
            mapping[name] = name
    return mapping
# ─────────────────────────────────────────────────────────────────────────────


# ─── v2.4: FILTRO PYTHON DE VERBAS (OPÇÃO B) ─────────────────────────────────
# Padrões que identificam CLARAMENTE lixo — não são verbas salariais.
# Complementa o prompt melhorado (Opção A): pega o que o Gemini ainda deixar passar.
_LIXO_PATTERNS = [
    r'https?://',                                    # URLs
    r'assinado eletronicamente',                     # assinaturas PJe
    r'n[uú]mero do (processo|documento)',            # metadados judiciais
    r'juntado em',                                   # metadado PJe
    r'^cnpj[\s:\-]',                                # CNPJ da empresa
    r'^cpf[\s:\-]',                                 # CPF
    r'fpff\d+',                                     # código de sistema
    r'^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}',          # timestamp puro
    r'^pje$',                                       # logo PJe
    r'^nome$',                                      # cabeçalho de coluna
    r'^c[oó]digo$',                                 # cabeçalho de coluna
    r'^descri[cç][aã]o$',                           # cabeçalho de coluna
    r'^refer[eê]ncia$',                             # cabeçalho de coluna
    r'^vencimentos$',                               # cabeçalho de coluna
    r'^descontos$',                                 # cabeçalho de coluna
    r'^compet[eê]ncia$',                            # cabeçalho de coluna
    r'declaro ter recebido',                        # texto legal
    r'assinatura do (funcion|empregado)',            # campo de assinatura
    r'liquidado na conta',                          # texto descritivo do holerite
]

def is_verba_valida(item: str) -> bool:
    """
    Retorna True se o item parece uma verba salarial legítima.
    Filtra lixo que o Gemini pode devolver mesmo com prompt melhorado (Opção A).

    Regras:
      - Mínimo 3 caracteres
      - Máximo 80 caracteres (assinaturas longas têm mais)
      - Sem sequência de 7+ dígitos (números de processo/documento)
      - Não casa com nenhum dos padrões de lixo conhecidos
    """
    s = item.strip()
    if len(s) < 3:
        return False
    if len(s) > 80:
        return False
    # Sequência longa de dígitos → número de processo/documento/hash
    if re.search(r'\d{7,}', s):
        return False
    s_lower = s.lower()
    for pattern in _LIXO_PATTERNS:
        if re.search(pattern, s_lower):
            return False
    return True
# ─────────────────────────────────────────────────────────────────────────────


# ─── v2.6: STRIP DE VALORES EMBUTIDOS NOS NOMES ──────────────────────────────
def strip_trailing_value(item: str) -> str:
    """
    Remove valor numérico colado ao final do nome da verba.
    O Gemini às vezes devolve "campo: valor" como se fosse o nome do item.

    Exemplos:
      "Media H.E. (130): 3,17"           → "Media H.E. (130)"
      "13° Salario: 243,64"              → "13° Salario"
      "Salário Base: 1.461,83"           → "Salário Base"
      "INSS s/ 130 Referência: 8,00"     → "INSS s/ 130"
      "INSS"                             → "INSS"        (sem alteração)
      "Horas Extras 50%"                 → "Horas Extras 50%"  (sem alteração)
    """
    s = item.strip()
    # Remove ": número" do final (com ou sem sinal negativo, ponto/vírgula)
    s = re.sub(r'\s*:\s*-?[\d.,]+\s*$', '', s).strip()
    # Remove sufixo " Referência" que às vezes fica após strip acima
    s = re.sub(r'\s+Refer[eê]ncia\s*$', '', s, flags=re.IGNORECASE).strip()
    # Se ficou muito curto, retorna original
    return s if len(s) >= 3 else item.strip()


# ─── v2.6: FUZZY DEDUP DE VERBAS ─────────────────────────────────────────────
def _mesmos_numeros(a: str, b: str) -> bool:
    """
    Retorna True se os números nas duas norm_keys são idênticos.
    Impede que verbas como 'HE 50%' e 'HE 100%' sejam unidas,
    mesmo tendo ratio fuzzy alto.
    """
    return re.findall(r'\d+', a) == re.findall(r'\d+', b)


def fuzzy_dedup_verbas(verbas_dict, threshold=0.82):
    """
    Remove verbas com grafia ligeiramente diferente mas mesmo significado.
    Usa o PRIMEIRO encontrado como nome canônico.

    REGRA EXTRA: só une se os números nas duas strings forem idênticos.
    Isso impede fundir verbas que diferem apenas no percentual ou número:

      'HE 50%'     vs 'HE 100%'          → ratio 0.889, nums diferentes → SEPARADOS ✓
      'HE NOT 50%' vs 'HE NOT 100%'      → ratio 0.930, nums diferentes → SEPARADOS ✓
      'HE 50%'     vs 'HE Noturnas 50%'  → ratio 0.765 < 0.82           → SEPARADOS ✓

    O que AGRUPA corretamente:
      'Sal. Contr. INSS' vs 'Salário Contr. INSS' → ratio 0.857, sem nums → MERGE ✓
      'FGTS do Mes'      vs 'FGTS do Mês'         → ratio 1.000, sem nums → MERGE ✓

    Retorna novo dict {norm_key: display} sem duplicatas fuzzy.
    """
    canonical = []   # list of (norm_key, display_name)
    result    = {}

    for norm_key, display in verbas_dict.items():
        matched = False
        for c_key, _ in canonical:
            if (SequenceMatcher(None, norm_key, c_key).ratio() >= threshold
                    and _mesmos_numeros(norm_key, c_key)):
                matched = True
                break
        if not matched:
            canonical.append((norm_key, display))
            result[norm_key] = display

    return result
# ─────────────────────────────────────────────────────────────────────────────


def _generate_full_month_range(meses_list):
    """
    Dado uma lista de meses no formato 'MM/AAAA', retorna todos os meses
    entre o mais antigo e o mais recente (inclusive), em ordem cronológica.
    Meses sem dados no PDF ficam no Excel com valores '0'.
    """
    if not meses_list:
        return meses_list

    parsed = []
    for m in meses_list:
        try:
            dt = pd.to_datetime(m, format='%m/%Y')
            parsed.append(dt)
        except Exception:
            pass

    if not parsed:
        return meses_list

    full_range = pd.date_range(start=min(parsed), end=max(parsed), freq='MS')
    return [dt.strftime('%m/%Y') for dt in full_range]


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


class PayrollExtractorAI:
    # ── Gemini 2.5 Flash — preço USD por 1M tokens ────────────────────────
    PRICE_IN_PER_M  = 0.30   # input
    PRICE_OUT_PER_M = 2.50   # output (inclui thinking)
    USD_TO_BRL      = 5.70   # taxa aproximada apenas para display

    def __init__(self, job=None):
        self.job      = job
        self.client   = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model_id = "gemini-2.5-flash"

        # Acumuladores de tokens (thread-safe — várias páginas em paralelo)
        self._token_in   = 0
        self._token_out  = 0
        self._token_lock = Lock()

    def _track_usage(self, response):
        try:
            meta      = response.usage_metadata
            p_in      = getattr(meta, 'prompt_token_count',      0) or 0
            p_out     = getattr(meta, 'candidates_token_count',  0) or 0
            p_thought = getattr(meta, 'thoughts_token_count',    0) or 0
            with self._token_lock:
                self._token_in  += p_in
                self._token_out += p_out + p_thought
        except Exception:
            pass

    def _log_cost(self):
        cost_in   = (self._token_in  / 1_000_000) * self.PRICE_IN_PER_M
        cost_out  = (self._token_out / 1_000_000) * self.PRICE_OUT_PER_M
        total_usd = cost_in + cost_out
        total_brl = total_usd * self.USD_TO_BRL
        LOG('custo Gemini',
            f"{self._token_in:,} in + {self._token_out:,} out = "
            f"${total_usd:.4f}  (~R$ {total_brl:.4f})")

    def _process_single_page(self, page_bytes, p_num, prompt_type, targets=None):
        MAX_RETRIES = 2
        last_error  = None
        page_b64    = base64.standard_b64encode(page_bytes).decode('utf-8')

        for attempt in range(MAX_RETRIES + 1):
            try:
                if prompt_type == "analyze":
                    # ── v2.4/v2.6 OPÇÃO A: define por EXCLUSÃO o que não é verba ──
                    prompt = """Analise TODOS os HOLERITES da página. Ignore o Cartão Ponto.
Uma página pode conter MAIS DE UM holerite (mesmo funcionário em competências diferentes, ou funcionários diferentes).

1. Extraia o NOME DO FUNCIONÁRIO de CADA holerite (ignore o nome da empresa). Liste em "nomes".
2. Liste em "itens" todos os campos que representam valores monetários, horas, quantidades ou bases de cálculo relacionadas à remuneração — tanto os itens da tabela principal quanto os campos do rodapé (ex: Salário Base, Sal. Contr. INSS, Base Calc. FGTS, FGTS do Mês, Base Calc. IRRF, Faixa IRRF, etc.).

NÃO inclua em "itens":
- Assinaturas digitais ("Assinado eletronicamente por...", "Assinado em...")
- URLs e links (http://, https://)
- Números de processo ou documento judicial
- Timestamps e códigos de sistema (ex: "FPFF001.OPE 19/03/2024 14:29:32")
- CNPJ, CPF, endereços ou nome da empresa
- Cabeçalhos de coluna ("Descrição", "Referência", "Nome", "Código", "Vencimentos", "Descontos", "Competência")
- Textos legais ou informativos ("Declaro ter recebido...", "Juntado em", "Liquidado na conta...")
- Nomes de sistemas ou logos ("Pje", "eSocial")

REGRAS CRÍTICAS:
- Liste APENAS o NOME da verba/campo, SEM valores numéricos.
  CORRETO: "Media H.E. (13o)"   |   ERRADO: "Media H.E. (13o): 3,17"
  CORRETO: "Salário Base"       |   ERRADO: "Salário Base: 1.461,83"
- NÃO CRIE DUPLICADOS. Itens com apenas diferença de espaços ou pontos são o mesmo item.
- Exemplo: 'SALÁRIO CONTR.INSS' e 'SALÁRIO CONTR. INSS' → listar UMA VEZ.
- Não confunda 'Horas Extras 50%' com 'Horas Extras Noturnas 50%' — são itens DIFERENTES.
JSON: {"nomes": [], "itens": []}"""

                else:
                    targets_str = ', '.join(str(t) for t in (targets or []))
                    prompt = f"""Ignore o Cartão Ponto. No Holerite, extraia os dados com precisão:
JSON: {{"nome": "Nome", "periodo": "MM/AAAA", "dados": [{{"campo": "Item", "ref": "Ref", "valor": "Valor"}}]}}

Se a página contiver MAIS DE UM holerite (competências diferentes no mesmo funcionário OU funcionários diferentes), retorne um ARRAY JSON com um objeto completo por holerite (cada um com seu nome, periodo e dados).

DIFERENCIAÇÃO OBRIGATÓRIA:
- 'Horas Normais' é um item. 'Horas Normais Noturnas' é OUTRO item. Não troque os valores.
Extraia apenas: {targets_str}"""

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

                result = safe_parse_json(response.text)
                if result:
                    self._track_usage(response)
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
        pages      = self._parse_range_from_file(pdf_path, pages_range)
        total      = len(pages)
        t_inicio   = time.time()
        worker_pid = os.getpid()

        page_buffers, total_pdf = _presplit_pages(pdf_path, pages)

        LOG_SEP('HOLERITE — ANÁLISE INICIADA')
        LOG('job_id',       self.job.id if self.job else '?')
        LOG('worker PID',   str(worker_pid))
        LOG('páginas',      f"{total}  ({pages_range})")
        LOG('total no PDF', f"{total_pdf} páginas")
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

        # ── v2.4 OPÇÃO B + v2.6: filtro, strip de valores e fuzzy dedup ─────────
        filtrados = 0
        for p_num in sorted(results_by_page.keys()):
            data = results_by_page[p_num]
            for item in data.get('itens', []):
                clean = str(item).strip()

                # v2.6: remove valor numérico embutido no nome ("Salário Base: 1.461,83" → "Salário Base")
                clean = strip_trailing_value(clean)

                if not is_verba_valida(clean):
                    filtrados += 1
                    continue
                if '{' not in clean and len(clean) > 2 and not re.match(r'^[0-9\.,\-/%\s:]+$', clean):
                    norm_key = super_norm(clean)
                    if norm_key not in unique_items_ordered:
                        unique_items_ordered[norm_key] = clean
            for n in data.get('nomes', []):
                if is_valid_name(n):
                    name_upper = str(n).strip().upper()
                    name_key   = normalize_name_key(name_upper)
                    if name_key not in all_nomes:
                        all_nomes[name_key] = name_upper

        # v2.6: fuzzy dedup — agrupa verbas com grafia ligeiramente diferente
        # (ex: "Sal. Contr. INSS" e "Salário Contr. INSS" → fica só o primeiro)
        antes_fuzzy = len(unique_items_ordered)
        unique_items_ordered = fuzzy_dedup_verbas(unique_items_ordered, threshold=0.82)
        fuzzy_removidos = antes_fuzzy - len(unique_items_ordered)
        # ─────────────────────────────────────────────────────────────────────

        t_total = round(time.time() - t_inicio, 1)

        LOG_SEP('ANÁLISE CONCLUÍDA')
        LOG('tempo',          f"{t_total}s")
        LOG('verbas únicas',  str(len(unique_items_ordered)))
        if filtrados:
            LOG('itens filtrados (lixo)',    str(filtrados),       'WARN')
        if fuzzy_removidos:
            LOG('itens fundidos (fuzzy)',    str(fuzzy_removidos), 'WARN')
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
    def process_payroll_task(self, pdf_path, pages_range, selected_verbas,
                             user_email=None, known_names=None):
        job        = get_current_job()
        pages      = self._parse_range_from_file(pdf_path, pages_range)
        total      = len(pages)
        t_inicio   = time.time()
        worker_pid = os.getpid()

        page_buffers, total_pdf = _presplit_pages(pdf_path, pages)

        LOG_SEP('HOLERITE — EXTRAÇÃO INICIADA')
        LOG('job_id',    job.id)
        LOG('usuário',   user_email or '?')
        LOG('worker PID', str(worker_pid))
        LOG('páginas',   f"{total}  ({pages_range})")
        if known_names:
            LOG('nomes do scan', f"{len(known_names)} funcionário(s) esperado(s)")
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

        # Guarda resultados por página para poder ordenar depois (carry-forward)
        results_by_page_extract = {}   # {p_num: [lista de holerites]}
        erros                   = []
        completed_count         = 0

        with ThreadPoolExecutor(max_workers=min(MAX_GEMINI_WORKERS, total)) as executor:
            futures = {
                executor.submit(self._process_single_page, page_buffers[p], p, "process", clean_targets): p
                for p in pages if p in page_buffers
            }
            for future in as_completed(futures):
                p_num = futures[future]
                data  = future.result()
                if data:
                    if isinstance(data, list):
                        results_by_page_extract[p_num] = data
                        total_campos = sum(len(h.get('dados', [])) for h in data if isinstance(h, dict))
                        LOG(f'página {p_num}', f"ok — {len(data)} holerites, {total_campos} campos")
                    else:
                        results_by_page_extract[p_num] = [data]
                        LOG(f'página {p_num}', f"ok — 1 holerite, {len(data.get('dados', []))} campos")
                else:
                    erros.append(p_num)
                    LOG(f'página {p_num}', 'sem retorno', 'WARN')

                completed_count += 1
                job.meta.update({
                    'current_step': completed_count,
                    'message':      f"Extraindo página {p_num}...",
                })
                job.save_meta()

        if not results_by_page_extract:
            LOG('resultado', 'nenhum dado extraído — abortando', 'ERR ')
            job.meta.update({'status': 'error', 'error': 'Nenhum dado extraído das páginas.'})
            job.save_meta()
            return False

        # ── v2.5: Resolução de nomes por ordem de página ─────────────────────
        #
        # Percorre as páginas em ordem crescente (não a ordem de chegada dos
        # futures, que é aleatória). Para cada holerite sem nome válido aplica:
        #
        #   OPÇÃO 3 — se known_names tem exatamente 1 entrada: usa esse nome
        #             (caso mais comum: PDF de 1 único funcionário)
        #
        #   OPÇÃO 2 — carry-forward: herda o último nome válido visto antes,
        #             independente de quantos funcionários há no PDF
        #
        #   Último recurso — se ainda sem nome e known_names não vazio:
        #             usa known_names[0]
        #
        # Exemplos:
        #   pág 1 "VALMIR SCOTTA" | pág 2 "" → pág 2 recebe "VALMIR SCOTTA"
        #   pág 1 "" | pág 2 "VALMIR SCOTTA" → pág 1 sem nome (nada antes),
        #              pág 3 "" → pág 3 recebe "VALMIR SCOTTA"
        # ─────────────────────────────────────────────────────────────────────
        all_extracted   = []
        last_valid_name = None          # carry-forward
        nomes_sem_nome  = 0             # contador para log

        for p_num in sorted(results_by_page_extract.keys()):
            for holerite in results_by_page_extract[p_num]:
                nome = clean_value(holerite.get('nome', ''))

                if not is_valid_name(nome):
                    # OPÇÃO 3: único funcionário conhecido → atribui direto
                    if known_names and len(known_names) == 1:
                        nome = known_names[0]
                    # OPÇÃO 2: carry-forward do último nome válido visto
                    elif last_valid_name:
                        nome = last_valid_name
                    # Último recurso: primeiro nome do scan
                    elif known_names:
                        nome = known_names[0]
                    else:
                        nome = 'Funcionário Não Especificado'

                    holerite['nome'] = nome
                    nomes_sem_nome  += 1
                else:
                    # Nome válido → atualiza carry-forward
                    last_valid_name = nome

                all_extracted.append(holerite)

        if nomes_sem_nome:
            LOG('nomes resolvidos', f"{nomes_sem_nome} holerite(s) sem nome preenchidos por contexto", 'WARN')

        # ── Monta DataFrame ───────────────────────────────────────────────────
        output_path = os.path.join(tempfile.gettempdir(), f"Folha_{job.id}.xlsx")
        temp_data   = []
        for e in all_extracted:
            nome = clean_value(e.get('nome'))
            mes  = clean_value(e.get('periodo'))
            for item in e.get('dados', []):
                temp_data.append({
                    'Nome':  nome,
                    'Mês':   mes,
                    'Campo': clean_value(item.get('campo')),
                    'Ref':   format_br_number(clean_value(item.get('ref'))),
                    'Valor': format_br_number(clean_value(item.get('valor'))),
                })

        df_full = pd.DataFrame(temp_data)

        # ── Filtro de nomes claramente inválidos (empresa, cabeçalhos, etc.) ──
        # Neste ponto todos os holerites sem nome já foram resolvidos acima.
        # Este filtro descarta apenas registros cujo nome ainda é inválido
        # (ex: Gemini retornou "HOSPITAL MONTENEGRO" ou "Nome") e que não
        # batem com nenhum nome do scan e nem passam em is_valid_name.
        if known_names and len(known_names) > 0:
            known_keys = [normalize_name_key(n) for n in known_names]

            def nome_bate_known(nome):
                if not nome or nome in ('0', '', 'Funcionário Não Especificado'):
                    return True   # já foi resolvido acima — mantém
                nome_key = normalize_name_key(nome)
                for k in known_keys:
                    if SequenceMatcher(None, nome_key, k).ratio() >= 0.75:
                        return True
                return is_valid_name(nome)

            antes = len(df_full)
            df_full = df_full[df_full['Nome'].apply(nome_bate_known)].copy()
            depois  = len(df_full)
            if antes != depois:
                LOG('registros removidos', f"{antes - depois} linha(s) com nomes inválidos", 'WARN')

        if df_full.empty:
            LOG('resultado', 'DataFrame vazio após filtro de nomes — abortando', 'ERR ')
            job.meta.update({'status': 'error', 'error': 'Nenhum dado válido após filtro de nomes.'})
            job.save_meta()
            return False

        # ── v2.4: Fuzzy grouping — nomes similares vão para a mesma aba ──────
        nomes_unicos   = df_full['Nome'].unique().tolist()
        name_canon_map = fuzzy_group_names(nomes_unicos, threshold=0.82)
        df_full['Nome_key'] = df_full['Nome'].apply(
            lambda n: normalize_name_key(name_canon_map.get(n, n))
        )
        # Mapeia chave normalizada → nome display canônico
        name_map = {}
        for orig, canon in name_canon_map.items():
            k = normalize_name_key(canon)
            if k not in name_map:
                name_map[k] = canon

        abas      = 0
        nomes_abas = []

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for nome_key, group in df_full.groupby('Nome_key'):
                nome_display = name_map.get(nome_key, nome_key)
                meses_com_dados = sorted(
                    group['Mês'].unique(),
                    key=lambda x: pd.to_datetime(x, format='%m/%Y', errors='coerce')
                )
                meses  = _generate_full_month_range(meses_com_dados)
                df_aba = pd.DataFrame(index=meses, columns=multi_col).fillna('0')
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

        t_total = round(time.time() - t_inicio, 1)
        xlsx_kb = round(os.path.getsize(output_path) / 1024, 1)

        LOG_SEP('EXTRAÇÃO CONCLUÍDA')
        LOG('tempo',   f"{t_total}s")
        LOG('arquivo', f"Folha_{job.id}.xlsx  ({xlsx_kb} KB)")
        if erros:
            LOG('páginas sem retorno', str(erros), 'WARN')
        LOG_TABLE(f"ABAS GERADAS — {abas} FUNCIONÁRIO(S)", nomes_abas)
        self._log_cost()
        LOG_SEP()

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

def process_payroll_final_task(pdf_path, pages, selected_verbas, user_id, known_names=None):
    return PayrollExtractorAI(job=get_current_job()).process_payroll_task(
        pdf_path, pages, selected_verbas,
        user_email=user_id,
        known_names=known_names or []
    )
