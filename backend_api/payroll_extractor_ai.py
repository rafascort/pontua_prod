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

def normalize_text(text):
    """Remove acentos e padroniza para evitar itens duplicados no filtro."""
    if not text: return ""
    text = str(text).strip().lower()
    text = "".join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    return text

class PayrollExtractorAI:
    def __init__(self, job=None):
        self.job = job
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key: raise ValueError("Chave GEMINI_API_KEY não configurada.")
        self.client = genai.Client(api_key=api_key)
        # Utilizando o modelo 2.5-flash da sua lista para maior inteligência visual
        self.model_id = "gemini-2.5-flash"

    def _parse_range(self, pages_str):
        res = []
        if not pages_str: return []
        for part in pages_str.split(','):
            part = part.strip()
            if '-' in part:
                try:
                    s, e = map(int, part.split('-'))
                    res.extend(range(s, e + 1))
                except: pass
            elif part.isdigit(): res.append(int(part))
        return sorted(list(set(p for p in res if p > 0)))

    def _wait_for_file(self, file_name):
        file = self.client.files.get(name=file_name)
        while file.state.name == "PROCESSING":
            time.sleep(1)
            file = self.client.files.get(name=file_name)
        return file

    def scan_verbas_task(self, pdf_path, pages_range):
        """Identifica todos os itens de holerite em todas as páginas, ignorando o ponto."""
        pages = self._parse_range(pages_range)
        reader = PdfReader(pdf_path)
        global_map = {} 
        all_nomes = set()

        for p_num in pages:
            try:
                writer = PdfWriter()
                writer.add_page(reader.pages[p_num - 1])
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                    writer.write(tmp.name)
                    tmp_path = tmp.name

                uploaded_file = self.client.files.upload(file=tmp_path)
                file = self._wait_for_file(uploaded_file.name)
                
                prompt = """Analise este documento. Ele contém um HOLERITE e um CARTÃO PONTO na mesma folha.
                REGRA CRÍTICA: Ignore COMPLETAMENTE a parte de 'BATIDAS', horários ou cartão ponto.
                Foque apenas no Demonstrativo de Pagamento (Holerite).
                Extraia em JSON:
                1. 'nomes': Lista com o nome completo do funcionário.
                2. 'itens': Lista com os nomes das verbas, descontos e bases (ex: Salário Base, INSS, FGTS).
                NÃO extraia valores numéricos agora."""
                
                response = self.client.models.generate_content(model=self.model_id, contents=[file, prompt])
                self.client.files.delete(name=file.name)
                os.unlink(tmp_path)

                data = json.loads(re.search(r'\{.*\}', response.text, re.DOTALL).group())
                
                for item in data.get('itens', []):
                    val = str(item).strip()
                    if not re.match(r'^[\d.,/-]+$', val) and len(val) > 2:
                        key = normalize_text(val)
                        if key not in global_map: global_map[key] = val
                
                for nome in data.get('nomes', []):
                    all_nomes.add(str(nome).strip().upper())
            except: continue

        result = {
            "nomes": sorted(list(all_nomes)),
            "verbas": list(global_map.values()), # Ordem visual mantida
            "pdf_path": pdf_path, "pages": pages_range
        }
        if self.job:
            self.job.meta.update({'status': 'completed', 'result': result})
            self.job.save_meta()
        return result

    def process_payroll_task(self, pdf_path, pages_range, selected_verbas):
        """Gera o Excel com colunas fixas, abas por pessoa e preenchimento de 0."""
        job = get_current_job()
        pages = self._parse_range(pages_range)
        job.meta.update({'total_steps': len(pages), 'current_step': 0, 'status': 'processing'})
        job.save_meta()

        # Lista Mestra de Colunas baseada na sua seleção
        clean_targets = [str(v).strip() for v in selected_verbas]
        master_cols = ['Mês'] + clean_targets
        
        all_results = []
        reader = PdfReader(pdf_path)

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
                
                prompt = f"""Atue como especialista em holerites. Ignore o Cartão Ponto nesta folha.
                Extraia apenas os dados do HOLERITE.
                JSON: {{'nome': 'Nome', 'periodo': 'MM/AAAA', 'dados': [{{'campo': 'Item', 'valor': 'Valor'}}]}}
                Campos alvo: {clean_targets}"""
                
                response = self.client.models.generate_content(model=self.model_id, contents=[file, prompt])
                self.client.files.delete(name=file.name)
                os.unlink(tmp_path)

                match = re.search(r'\[.*\]|\{.*\}', response.text, re.DOTALL)
                if match:
                    d = json.loads(match.group())
                    all_results.extend(d if isinstance(d, list) else [d])
            except: continue

        if not all_results: return False

        output_path = os.path.join(tempfile.gettempdir(), f"Folha_{job.id}.xlsx")
        
        # Consolidação plana dos dados
        flat_rows = []
        for entry in all_results:
            n, m = entry.get('nome', 'N/A'), entry.get('periodo', 'N/A')
            for item in entry.get('dados', []):
                flat_rows.append({'Nome': n, 'Mês': m, 'Campo': item.get('campo'), 'Valor': item.get('valor')})

        df_master = pd.DataFrame(flat_rows)
        if df_master.empty: return False

        # Criação do Excel real (.xlsx)
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for nome, group in df_master.groupby('Nome'):
                # Pivot: Mês como linha, Verbas como colunas
                df_p = group.pivot_table(index='Mês', columns='Campo', values='Valor', aggfunc='first').reset_index()
                
                # REINDEX: Força todas as colunas selecionadas e preenche vazios com '0'
                df_p = df_p.reindex(columns=master_cols, fill_value='0')
                
                # Ordenação Cronológica (MM/AAAA)
                df_p['dt'] = pd.to_datetime(df_p['Mês'], format='%m/%Y', errors='coerce')
                df_p = df_p.sort_values('dt').drop('dt', axis=1)
                
                sheet_name = re.sub(r'[^a-zA-Z0-9 ]', '', str(nome))[:31]
                df_p.to_excel(writer, sheet_name=sheet_name, index=False)

        job.meta.update({'status': 'completed', 'file_path': output_path})
        job.save_meta()
        return True

def scan_verbas_task(pdf_path, pages, user_id):
    return PayrollExtractorAI(job=get_current_job()).scan_verbas_task(pdf_path, pages)

def process_payroll_final_task(pdf_path, pages, selected_verbas, user_id):
    return PayrollExtractorAI(job=get_current_job()).process_payroll_task(pdf_path, pages, selected_verbas)
