# /opt/pontua/AutoPonto/backend_api/payroll_extractor_ai.py
import os
import tempfile
import pandas as pd
import json
import logging
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed # Adicionado as_completed
from google import genai 
from rq import get_current_job
from pypdf import PdfReader, PdfWriter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PayrollAI")

def clean_value(val):
    if isinstance(val, dict):
        return str(next(iter(val.values()))) if val else "0"
    return str(val).strip() if val is not None else "0"

def is_valid_name(name):
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

    def _process_single_page(self, pdf_path, p_num, prompt_type, targets=None):
        """Lógica individual para processamento de uma página."""
        try:
            reader = PdfReader(pdf_path)
            writer = PdfWriter()
            writer.add_page(reader.pages[p_num - 1])
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                writer.write(tmp.name)
                tmp_path = tmp.name

            uploaded_file = self.client.files.upload(file=tmp_path)
            file = self.client.files.get(name=uploaded_file.name)
            while file.state.name == "PROCESSING":
                time.sleep(1)
                file = self.client.files.get(name=uploaded_file.name)

            if prompt_type == "analyze":
                prompt = """Analise o HOLERITE. Ignore o Cartão Ponto.
                1. Extraia o NOME DO FUNCIONÁRIO (Ignore empresa).
                2. Liste VERBAS na ordem exata de CIMA PARA BAIXO.
                REGRA: Não envie objetos JSON complexos na lista de itens, apenas o nome da verba.
                JSON: {'nomes': [], 'itens': []}"""
            else:
                prompt = f"""Ignore o Cartão Ponto. No Holerite, extraia:
                JSON: {{'nome': 'Nome', 'periodo': 'MM/AAAA', 'dados': [{{'campo': 'Item', 'ref': 'Ref', 'valor': 'Valor'}}]}}
                Extraia apenas: {targets}"""

            response = self.client.models.generate_content(model=self.model_id, contents=[file, prompt])
            self.client.files.delete(name=file.name)
            os.unlink(tmp_path)
            return json.loads(re.search(r'\{.*\}', response.text, re.DOTALL).group())
        except Exception as e:
            logger.error(f"Erro na página {p_num}: {e}")
            return None

    def scan_verbas_task(self, pdf_path, pages_range):
        """Identificação inicial paralela com atualização de progresso em tempo real."""
        reader = PdfReader(pdf_path)
        pages = self._parse_range(pages_range, len(reader.pages))
        total = len(pages)
        
        if self.job:
            self.job.meta.update({'total_steps': total, 'current_step': 0, 'status': 'processing', 'message': 'A iniciar análise...'})
            self.job.save_meta()

        unique_items_ordered = {} 
        all_nomes = set()
        results_by_page = {}

        # Processamento paralelo com as_completed para atualizar a barra de progresso
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(self._process_single_page, pdf_path, p, "analyze"): p for p in pages}
            completed_count = 0

            for future in as_completed(futures):
                p_num = futures[future]
                data = future.result()
                if data:
                    results_by_page[p_num] = data
                
                completed_count += 1
                if self.job:
                    self.job.meta.update({'current_step': completed_count, 'message': f"Página {p_num} analisada..."})
                    self.job.save_meta()

        # Consolidar resultados respeitando a ordem original do PDF (cima para baixo)
        for p_num in sorted(results_by_page.keys()):
            data = results_by_page[p_num]
            for item in data.get('itens', []):
                clean = str(item).strip()
                if '{' not in clean and len(clean) > 2:
                    norm = "".join(c for c in unicodedata.normalize('NFD', clean.lower()) if unicodedata.category(c) != 'Mn')
                    if norm not in unique_items_ordered:
                        unique_items_ordered[norm] = clean
            for n in data.get('nomes', []):
                if is_valid_name(n): all_nomes.add(str(n).strip().upper())

        result = {"nomes": sorted(list(all_nomes)), "verbas": list(unique_items_ordered.values()), "pdf_path": pdf_path, "pages": pages_range}
        if self.job: self.job.meta.update({'status': 'completed', 'result': result}); self.job.save_meta()
        return result

    def process_payroll_task(self, pdf_path, pages_range, selected_verbas):
        """Geração de Excel paralela com atualização de progresso em tempo real."""
        job = get_current_job()
        reader = PdfReader(pdf_path)
        pages = self._parse_range(pages_range, len(reader.pages))
        total = len(pages)
        
        job.meta.update({'total_steps': total, 'current_step': 0, 'status': 'processing', 'message': 'A preparar extração...'})
        job.save_meta()

        clean_targets = [str(v).strip() for v in selected_verbas]
        col_tuples = [(target, sub) for target in clean_targets for sub in ['Ref.', 'Valor']]
        multi_col = pd.MultiIndex.from_tuples(col_tuples)

        all_extracted = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(self._process_single_page, pdf_path, p, "process", clean_targets): p for p in pages}
            completed_count = 0

            for future in as_completed(futures):
                p_num = futures[future]
                data = future.result()
                if data:
                    all_extracted.append(data)
                
                completed_count += 1
                job.meta.update({'current_step': completed_count, 'message': f"Dados da página {p_num} extraídos..."})
                job.save_meta()

        if not all_extracted: return False

        output_path = os.path.join(tempfile.gettempdir(), f"Folha_{job.id}.xlsx")
        temp_data = []
        for e in all_extracted:
            nome, mes = clean_value(e.get('nome')), clean_value(e.get('periodo'))
            for item in e.get('dados', []):
                temp_data.append({'Nome': nome, 'Mês': mes, 'Campo': clean_value(item.get('campo')), 'Ref': clean_value(item.get('ref')), 'Valor': clean_value(item.get('valor'))})
        
        df_full = pd.DataFrame(temp_data)
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for nome, group in df_full.groupby('Nome'):
                meses = sorted(group['Mês'].unique(), key=lambda x: pd.to_datetime(x, format='%m/%Y', errors='coerce'))
                df_aba = pd.DataFrame(index=meses, columns=multi_col).fillna('0')
                df_aba.index.name = 'Mês'
                for _, row in group.iterrows():
                    m, c = row['Mês'], row['Campo']
                    target = next((t for t in clean_targets if t.lower() in str(c).lower()), None)
                    if target:
                        df_aba.at[m, (target, 'Ref.')], df_aba.at[m, (target, 'Valor')] = row['Ref'], row['Valor']
                df_aba.to_excel(writer, sheet_name=re.sub(r'[^a-zA-Z0-9 ]', '', str(nome))[:31], index=True)

        job.meta.update({'status': 'completed', 'file_path': output_path}); job.save_meta()
        return True

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

def scan_verbas_task(pdf_path, pages, user_id):
    return PayrollExtractorAI(job=get_current_job()).scan_verbas_task(pdf_path, pages)

def process_payroll_final_task(pdf_path, pages, selected_verbas, user_id):
    return PayrollExtractorAI(job=get_current_job()).process_payroll_task(pdf_path, pages, selected_verbas)
