# /opt/pontua/AutoPonto/backend_api/payroll_extractor_ai.py
import os
import tempfile
import pandas as pd
import json
import logging
import re
import time
import unicodedata
from google import genai 
from rq import get_current_job
from pypdf import PdfReader, PdfWriter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PayrollAI")

def clean_value(val):
    """Garante que o valor seja uma string limpa, sem chaves de dicionário."""
    if isinstance(val, dict):
        return str(next(iter(val.values()))) if val else "0"
    return str(val).strip() if val is not None else "0"

def is_valid_name(name):
    """Filtra lixo de cabeçalho para não aparecer nos nomes dos funcionários."""
    if not name or len(name) < 8: return False
    forbidden = ["LTDA", "CNPJ", "CPF", "RUA", "AVENIDA", "ENDERECO", "EMPRESA", "S.A", "EIRELI"]
    name_up = name.upper()
    if any(word in name_up for word in forbidden): return False
    if len(re.findall(r'\d', name)) > 4: return False
    return True

class PayrollExtractorAI:
    def __init__(self, job=None):
        self.job = job
        api_key = os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-2.5-flash"

    def _call_ai_with_retry(self, file, prompt, retries=3):
        for i in range(retries):
            try:
                return self.client.models.generate_content(model=self.model_id, contents=[file, prompt])
            except Exception as e:
                if i < retries - 1:
                    time.sleep(5)
                    continue
                raise e

    def _parse_range(self, pages_str, total_pages):
        res = []
        if not pages_str: return []
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

    def _wait_for_file(self, file_name):
        file = self.client.files.get(name=file_name)
        while file.state.name == "PROCESSING":
            time.sleep(1)
            file = self.client.files.get(name=file_name)
        return file

    def scan_verbas_task(self, pdf_path, pages_range):
        """Passo 2: Identifica nomes e verbas (Agora com Barra de Progresso)."""
        reader = PdfReader(pdf_path)
        pages = self._parse_range(pages_range, len(reader.pages))
        
        # Inicia Meta de Progresso na Análise
        if self.job:
            self.job.meta.update({
                'total_steps': len(pages), 
                'current_step': 0, 
                'status': 'processing', 
                'message': 'Iniciando análise do documento...'
            })
            self.job.save_meta()

        unique_items_ordered = {} 
        all_nomes = set()

        for index, p_num in enumerate(pages):
            try:
                # Atualiza progresso a cada página lida
                if self.job:
                    self.job.meta.update({
                        'current_step': index + 1, 
                        'message': f"Analisando verbas na página {p_num}..."
                    })
                    self.job.save_meta()

                writer = PdfWriter()
                writer.add_page(reader.pages[p_num - 1])
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                    writer.write(tmp.name)
                    tmp_path = tmp.name

                uploaded_file = self.client.files.upload(file=tmp_path)
                file = self._wait_for_file(uploaded_file.name)
                
                prompt = """Aja como analista de DP. No HOLERITE:
                1. Extraia o NOME DO FUNCIONÁRIO (Ignore empresa).
                2. Liste VERBAS na ordem exata de CIMA PARA BAIXO.
                REGRA: Não envie objetos JSON complexos na lista de itens, apenas o nome da verba.
                JSON: {'nomes': [], 'itens': []}"""
                
                response = self._call_ai_with_retry(file, prompt)
                self.client.files.delete(name=file.name)
                os.unlink(tmp_path)

                data = json.loads(re.search(r'\{.*\}', response.text, re.DOTALL).group())
                
                for item in data.get('itens', []):
                    clean = str(item).strip()
                    # Bloqueio de JSON e lixo na lista de seleção
                    if '{' not in clean and len(clean) > 2 and not re.match(r'^[0-9\.,\-/%\s:]+$', clean):
                        norm = "".join(c for c in unicodedata.normalize('NFD', clean.lower()) if unicodedata.category(c) != 'Mn')
                        if norm not in unique_items_ordered:
                            unique_items_ordered[norm] = clean
                
                for n in data.get('nomes', []):
                    if is_valid_name(n):
                        all_nomes.add(str(n).strip().upper())
            except: continue

        result = {
            "nomes": sorted(list(all_nomes)),
            "verbas": list(unique_items_ordered.values()),
            "pdf_path": pdf_path, "pages": pages_range
        }
        
        if self.job:
            self.job.meta.update({'status': 'completed', 'result': result})
            self.job.save_meta()
        return result

    def process_payroll_task(self, pdf_path, pages_range, selected_verbas):
        """Passo 4: Gera Excel MultiIndex (Sub-colunas)."""
        job = get_current_job()
        reader = PdfReader(pdf_path)
        pages = self._parse_range(pages_range, len(reader.pages))
        
        job.meta.update({'total_steps': len(pages), 'current_step': 0, 'status': 'processing'})
        job.save_meta()

        clean_targets = [str(v).strip() for v in selected_verbas]
        col_tuples = [(target, sub) for target in clean_targets for sub in ['Ref.', 'Valor']]
        multi_col = pd.MultiIndex.from_tuples(col_tuples)
        
        all_extracted = []
        for index, p_num in enumerate(pages):
            try:
                job.meta.update({'current_step': index + 1, 'message': f"Processando página {p_num}..."})
                job.save_meta()

                writer = PdfWriter()
                writer.add_page(reader.pages[p_num - 1])
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                    writer.write(tmp.name)
                    tmp_path = tmp.name

                uploaded_file = self.client.files.upload(file=tmp_path)
                file = self._wait_for_file(uploaded_file.name)
                
                prompt = f"""Ignore o Cartão Ponto. No Holerite, transcreva literal:
                JSON: {{'nome': 'Nome', 'periodo': 'MM/AAAA', 'dados': [{{'campo': 'Item', 'ref': 'Ref', 'valor': 'Valor'}}]}}
                Extraia apenas: {clean_targets}"""
                
                response = self._call_ai_with_retry(file, prompt)
                self.client.files.delete(name=file.name)
                os.unlink(tmp_path)

                match = re.search(r'\[.*\]|\{.*\}', response.text, re.DOTALL)
                if match:
                    d = json.loads(match.group())
                    all_extracted.extend(d if isinstance(d, list) else [d])
            except: continue

        if not all_extracted: return False

        output_path = os.path.join(tempfile.gettempdir(), f"Folha_{job.id}.xlsx")
        temp_data = []
        for e in all_extracted:
            nome, mes = clean_value(e.get('nome')), clean_value(e.get('periodo'))
            for item in e.get('dados', []):
                temp_data.append({
                    'Nome': nome, 'Mês': mes, 
                    'Campo': clean_value(item.get('campo')), 
                    'Ref': clean_value(item.get('ref')), 
                    'Valor': clean_value(item.get('valor'))
                })
        
        df_full = pd.DataFrame(temp_data)
        if df_full.empty: return False

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for nome, group in df_full.groupby('Nome'):
                meses = sorted(group['Mês'].unique(), key=lambda x: pd.to_datetime(x, format='%m/%Y', errors='coerce'))
                df_aba = pd.DataFrame(index=meses, columns=multi_col).fillna('0')
                df_aba.index.name = 'Mês'
                
                for _, row in group.iterrows():
                    m, c = row['Mês'], row['Campo']
                    target = next((t for t in clean_targets if t.lower() in c.lower()), None)
                    if target:
                        df_aba.at[m, (target, 'Ref.')] = row['Ref']
                        df_aba.at[m, (target, 'Valor')] = row['Valor']
                
                sheet_name = re.sub(r'[^a-zA-Z0-9 ]', '', str(nome))[:31]
                df_aba.to_excel(writer, sheet_name=sheet_name, index=True)

        job.meta.update({'status': 'completed', 'file_path': output_path})
        job.save_meta()
        return True

def scan_verbas_task(pdf_path, pages, user_id):
    return PayrollExtractorAI(job=get_current_job()).scan_verbas_task(pdf_path, pages)

def process_payroll_final_task(pdf_path, pages, selected_verbas, user_id):
    return PayrollExtractorAI(job=get_current_job()).process_payroll_task(pdf_path, pages, selected_verbas)
