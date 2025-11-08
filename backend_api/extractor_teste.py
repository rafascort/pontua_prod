# /opt/pontua/AutoPonto/backend_api/extractor_teste.py
import os
import re
import json
import time
import shutil
import tempfile
import pandas as pd
from io import BytesIO
from datetime import datetime
from rq import get_current_job
from google.cloud import documentai_v1 as documentai
from google.cloud import storage
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from unidecode import unidecode
import traceback

class ExtractorTesteBatch:
    """
    Classe para o Modelo Teste (Admin) que combina:
    1. Fluxo de Período (como extractor_geral_ai.py)
    2. Processamento em Lote GCS (como extractor_geral.py)
    """
    def __init__(self, job=None):
        self.job = job
        
        # --- Padrão de Inicialização (baseado em extractor_geral.py) ---
        self.project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        self.location = os.getenv('DOCAI_PROCESSOR_LOCATION', 'us')
        self.processor_id = os.getenv('DOCAI_PROCESSOR_ID')
        self.gcs_bucket_name = os.getenv('GCS_BUCKET_NAME')
        
        if not all([self.project_id, self.location, self.processor_id, self.gcs_bucket_name]):
            raise ValueError("Variáveis de ambiente (PROJECT, LOCATION, PROCESSOR, BUCKET) não configuradas.")

        self.storage_client = storage.Client(project=self.project_id)
        
        docai_client_options = {"api_endpoint": f"{self.location}-documentai.googleapis.com"}
        self.docai_client = documentai.DocumentProcessorServiceClient(
            client_options=docai_client_options
        )
        # --- Fim do Padrão de Inicialização ---

    def update_progress(self, current, total, message, status='processing'):
        if self.job:
            progress = int((current / total) * 100) if total > 0 else 0
            self.job.meta.update({
                'progress': progress,
                'current_step': current,
                'total_steps': total,
                'message': message,
                'status': status
            })
            self.job.save_meta()
            print(f"[LOG][Job {self.job.id}] Progresso: {progress}% - {message}")

    def upload_to_gcs(self, local_path, blob_name):
        """Faz upload de um arquivo local para o GCS."""
        print(f"[LOG][Job {self.job.id}] Uploading {local_path} para gs://{self.gcs_bucket_name}/{blob_name}")
        bucket = self.storage_client.bucket(self.gcs_bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(local_path)
        return f"gs://{self.gcs_bucket_name}/{blob_name}"

    def batch_process(self, gcs_input_uri, gcs_output_prefix):
        """Inicia um job de processamento em lote (assíncrono)."""
        name = self.docai_client.processor_path(self.project_id, self.location, self.processor_id)

        input_config = documentai.BatchDocumentsInputConfig(
            gcs_documents=documentai.GcsDocuments(
                documents=[documentai.GcsDocument(gcs_uri=gcs_input_uri, mime_type="application/pdf")]
            )
        )
        output_config = documentai.DocumentOutputConfig(
            gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(
                gcs_uri=f"gs://{self.gcs_bucket_name}/{gcs_output_prefix}"
            )
        )

        request = documentai.BatchProcessRequest(
            name=name,
            input_documents=input_config,
            document_output_config=output_config,
        )

        print(f"[LOG][Job {self.job.id}] Iniciando Batch Process no Document AI...")
        operation = self.docai_client.batch_process_documents(request)
        
        print(f"[LOG][Job {self.job.id}] Aguardando conclusão do job (Timeout: 2h)...")
        return operation.result(timeout=7200) # Timeout de 2 horas

    def download_results(self, gcs_output_prefix, local_dir):
        """Baixa os arquivos JSON resultantes do GCS para um diretório local."""
        print(f"[LOG][Job {self.job.id}] Baixando resultados de gs://{self.gcs_bucket_name}/{gcs_output_prefix}")
        bucket = self.storage_client.bucket(self.gcs_bucket_name)
        blobs = list(bucket.list_blobs(prefix=gcs_output_prefix))

        json_files = []
        for blob in blobs:
            if blob.name.endswith(".json"):
                local_path = os.path.join(local_dir, os.path.basename(blob.name))
                blob.download_to_filename(local_path)
                json_files.append(local_path)
                print(f"[LOG][Job {self.job.id}] Baixado: {blob.name}")
        
        return sorted(json_files) # Ordena para manter sequência de páginas

    def cleanup_gcs_files(self, gcs_input_blob, gcs_output_prefix):
        """Limpa arquivos de input e output do bucket GCS."""
        try:
            print(f"[LOG][Job {self.job.id}] Limpando arquivos GCS...")
            bucket = self.storage_client.bucket(self.gcs_bucket_name)
            
            # Deleta input
            blob_in = bucket.blob(gcs_input_blob)
            if blob_in.exists():
                blob_in.delete()

            # Deleta outputs
            blobs_out = list(bucket.list_blobs(prefix=gcs_output_prefix))
            for blob in blobs_out:
                blob.delete()
            print(f"[LOG][Job {self.job.id}] Limpeza GCS concluída.")
        except Exception as e:
            print(f"⚠️ [LOG][Job {self.job.id}] Erro ao limpar GCS: {e}")

    # --- Lógica de Extração (Copiada do extractor_geral_ai.py) ---
    def format_ai_rows_by_order(self, entities):
        """
        Extrai entidades 'tabela_marcacoes' ordenadas.
        """
        extracted_rows = []
        for entity in entities:
            if entity.type_.lower() == 'tabela_marcacoes' and entity.properties:
                row_data = {prop.type_.lower(): prop.mention_text.strip() for prop in entity.properties}
                extracted_rows.append({
                    'Entrada1': row_data.get('entrada1', '0'), 'Saida1': row_data.get('saida1', '0'),
                    'Entrada2': row_data.get('entrada2', '0'), 'Saida2': row_data.get('saida2', '0'),
                    'Entrada3': row_data.get('entrada3', '0'), 'Saida3': row_data.get('saida3', '0'),
                })
        return extracted_rows

# --- Lógica de Normalização (Copiada do extractor_geral_ai.py) ---
def normalize_time_format(value):
    """
    Normaliza horários para HH:MM.
    """
    if pd.isna(value) or value == "0" or value == 0 or value == "":
        return "0"
    value_str = str(value).strip()
    if value_str == "0" or value_str == "": return "0"
    
    match = re.search(r'(\d{1,2})[^\d](\d{2})', value_str)
    if match:
        hour = match.group(1).zfill(2)
        minute = match.group(2)
        return f"{hour}:{minute}"
    
    if len(value_str) == 4 and value_str.isdigit():
        return f"{value_str[:2]}:{value_str[2:]}"
    if len(value_str) == 3 and value_str.isdigit():
        return f"0{value_str[0]}:{value_str[1:]}"
    
    return "0"

# --- Função Principal da Tarefa ---
def process_pdf_task(pdf_path, pages_with_periods, model_type, user_id=None):
    job = get_current_job()
    if not job: 
        print("[ERRO FATAL] Não foi possível obter o Job do RQ.")
        return None
    
    extractor = ExtractorTesteBatch(job)
    
    temp_dir = tempfile.mkdtemp(prefix=f"batch_test_{job.id}_")
    local_batch_pdf = os.path.join(temp_dir, "batch_input.pdf")
    
    gcs_input_blob = f"{job.id}/input/batch.pdf"
    gcs_output_prefix = f"{job.id}/output/"

    try:
        extractor.update_progress(1, 5, "Preparando PDF para lote...")
        
        # 1. Criar PDF recortado (Lógica do Modelo 6)
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        
        sorted_pages = sorted(pages_with_periods, key=lambda x: x['page_number'])
        page_map = {}
        
        for i, p_info in enumerate(sorted_pages):
            original_idx = p_info['page_index'] # 0-based
            if 0 <= original_idx < len(reader.pages):
                writer.add_page(reader.pages[original_idx])
                
                # Guarda info original, mapeando do NOVO índice (i)
                p_info['original_filename'] = os.path.basename(pdf_path)
                p_info['start_date_obj'] = datetime.strptime(p_info['period']['start_date'], '%d/%m/%Y')
                p_info['end_date_obj'] = datetime.strptime(p_info['period']['end_date'], '%d/%m/%Y')
                page_map[i] = p_info
            else:
                print(f"AVISO: Página {p_info['page_number']} (idx {original_idx}) fora do range.")

        if not page_map: raise ValueError("Nenhuma página válida selecionada.")
        
        with open(local_batch_pdf, 'wb') as f: writer.write(f)
        print(f"[LOG][Job {job.id}] PDF recortado criado em {local_batch_pdf} com {len(page_map)} páginas.")

        # 2. Upload para GCS (Lógica do Modelo 7)
        extractor.update_progress(2, 5, "Enviando para processamento em nuvem...")
        gcs_input_uri = extractor.upload_to_gcs(local_batch_pdf, gcs_input_blob)

        # 3. Iniciar Batch Process (Lógica do Modelo 7)
        extractor.update_progress(3, 5, "Aguardando análise da IA (pode demorar)...")
        extractor.batch_process(gcs_input_uri, gcs_output_prefix)

        # 4. Baixar e Processar Resultados
        extractor.update_progress(4, 5, "Consolidando resultados...")
        json_files = extractor.download_results(gcs_output_prefix, temp_dir)
        
        all_page_dataframes = []
        global_page_idx = 0

        if not json_files: raise ValueError("Processamento da IA não retornou arquivos de resultado.")

        for json_file in json_files:
            with open(json_file, 'r', encoding='utf-8') as f:
                response_json = f.read()
                if not response_json:
                    print(f"AVISO: Arquivo JSON {json_file} está vazio.")
                    continue
                response = documentai.Document.from_json(response_json)
            
            # Processa cada página DENTRO do JSON
            for page in response.pages:
                original_info = page_map.get(global_page_idx)
                if not original_info:
                    print(f"ERRO: Página {global_page_idx} do resultado não encontrada no page_map.")
                    global_page_idx += 1
                    continue
                
                print(f"[LOG][Job {job.id}] Processando pág. lote {global_page_idx} (Original: {original_info['page_number']})")
                
                # --- Lógica de extração (baseada no Modelo 6) ---
                start_date = original_info['start_date_obj']
                end_date = original_info['end_date_obj']
                calendar_df = pd.DataFrame(pd.date_range(start=start_date, end=end_date, freq='D'), columns=['Dia_dt'])
                calendar_df['original_page'] = original_info['page_number']
                
                ai_rows = extractor.format_ai_rows_by_order(page.entities) 
                ai_data_df = pd.DataFrame(ai_rows)
                
                period_df = pd.concat([calendar_df, ai_data_df], axis=1)
                all_page_dataframes.append(period_df)
                
                global_page_idx += 1
                # --- Fim da lógica de extração ---

        # 5. Gerar CSV Final (Lógica do Modelo 6)
        extractor.update_progress(5, 5, "Gerando relatório final...")
        if not all_page_dataframes: raise ValueError("Nenhum dado foi extraído.")
        
        print(f"[LOG][Job {job.id}] Consolidando {len(all_page_dataframes)} DataFrames de página.")
        full_final_df = pd.concat(all_page_dataframes, ignore_index=True)
        
        if 'Dia_dt' not in full_final_df.columns or full_final_df['Dia_dt'].isnull().all():
            raise ValueError("Não foi possível determinar datas válidas.")

        full_final_df = full_final_df.dropna(subset=['Dia_dt'])
        full_final_df = full_final_df.sort_values('Dia_dt').drop_duplicates(subset=['Dia_dt'], keep='last')
        
        min_date_overall = full_final_df['Dia_dt'].min()
        max_date_overall = full_final_df['Dia_dt'].max()
        overall_date_range = pd.date_range(start=min_date_overall, end=max_date_overall, freq='D')
        
        final_df = full_final_df.set_index('Dia_dt').reindex(overall_date_range).reset_index()
        final_df.rename(columns={'index': 'Dia_dt'}, inplace=True)

        final_df['Dia'] = final_df['Dia_dt'].dt.strftime('%d/%m/%Y')
        day_map_pt = {0: "seg", 1: "ter", 2: "qua", 3: "qui", 4: "sex", 5: "sab", 6: "dom"}
        final_df['Dia_Sema'] = final_df['Dia_dt'].dt.dayofweek.map(day_map_pt)
        
        colunas_finais = ['Dia', 'Dia_Sema', 'Entrada1', 'Saida1', 'Entrada2', 'Saida2', 'Entrada3', 'Saida3']
        for col in colunas_finais:
            if col not in final_df.columns:
                final_df[col] = "0"
        
        final_df = final_df[colunas_finais].fillna("0")
        
        print(f"[LOG][Job {job.id}] Normalizando formatos de hora...")
        time_columns = ['Entrada1', 'Saida1', 'Entrada2', 'Saida2', 'Entrada3', 'Saida3']
        for col in time_columns:
            if col in final_df.columns:
                final_df[col] = final_df[col].apply(normalize_time_format)
        
        output_filename = f"Resultado_TesteBatch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        output_path = os.path.join(tempfile.gettempdir(), output_filename)
        final_df.to_csv(output_path, index=False, sep=';', encoding='utf-8-sig')

        job.meta.update({
            'status': 'completed',
            'message': 'Concluído com sucesso!',
            'file_path': output_path,
            'filename': output_filename
        })
        job.save_meta()
        print(f"[LOG][Job {job.id}] SUCESSO. CSV: {output_path}")
        return output_path

    except Exception as e:
        error_msg = f"Erro no processamento batch (Admin): {str(e)}"
        print(f"ERRO FATAL [Job {job.id}]: {error_msg}")
        traceback.print_exc()
        job.meta.update({'status': 'error', 'error': error_msg})
        job.save_meta()
        raise
    finally:
        # Limpeza
        if os.path.exists(temp_dir): 
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"[LOG][Job {job.id}] Diretório temp local removido: {temp_dir}")
        if os.path.exists(pdf_path): 
            try:
                os.remove(pdf_path) # Remove o PDF original temporário
                print(f"[LOG][Job {job.id}] PDF original temp removido: {pdf_path}")
            except Exception as e:
                print(f"AVISO [Job {job.id}]: Falha ao remover PDF original {pdf_path}: {e}")
        
        # Limpa GCS
        extractor.cleanup_gcs_files(gcs_input_blob, gcs_output_prefix)
