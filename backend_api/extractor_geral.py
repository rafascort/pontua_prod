# /opt/pontua/AutoPonto/backend_api/extractor_geral.py
import os
import tempfile
import pandas as pd
from io import BytesIO
from datetime import datetime
from rq import get_current_job
from google.cloud import documentai_v1 as documentai
from google.cloud import storage
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
import re
import concurrent.futures
import threading
import traceback

class ExtractorGeral:
    def __init__(self, model_type='7', job=None):
        self.model_type = model_type
        self.job = job
        self.project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        self.location = os.getenv('DOCAI_PROCESSOR_LOCATION')
        self.processor_id = os.getenv('DOCAI_PROCESSOR_ID')
        self.gcs_bucket_name = os.getenv('GCS_BUCKET_NAME')
        self.storage_client = storage.Client()
        self.upload_counter = 0
        self.upload_lock = threading.Lock()
        self.download_counter = 0
        self.download_lock = threading.Lock()

    def update_progress(self, current, total, message, status='processing', extra_info=None):
        if self.job:
            progress = int((current / total) * 100) if total > 0 else 0
            meta_update = {
                'progress': progress, 'message': message, 'current_step': current,
                'total_steps': total, 'status': status, 'timestamp': datetime.now().isoformat()
            }
            if extra_info:
                meta_update.update(extra_info)
            self.job.meta.update(meta_update)
            self.job.save_meta()

    def upload_page_to_gcs(self, reader, page_idx, idx, total_pages):
        try:
            writer = PdfWriter()
            writer.add_page(reader.pages[page_idx])
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                writer.write(tmp_file)
                single_page_path = tmp_file.name
            try:
                bucket = self.storage_client.bucket(self.gcs_bucket_name)
                blob_name = f"{self.job.id}/input/page_{idx:05d}.pdf"
                gcs_input_uri = f"gs://{self.gcs_bucket_name}/{blob_name}"
                bucket.blob(blob_name).upload_from_filename(single_page_path)
                
                with self.upload_lock:
                    self.upload_counter += 1
                    self.update_progress(0, 3, "A fazer upload das páginas...", extra_info={'upload_progress': self.upload_counter, 'upload_total': total_pages, 'upload_message': f"Upload: {self.upload_counter}/{total_pages} páginas"})
                return idx, documentai.GcsDocument(gcs_uri=gcs_input_uri, mime_type="application/pdf")
            finally:
                if os.path.exists(single_page_path): os.unlink(single_page_path)
        except Exception:
            return None, None

    def cleanup_gcs_files(self):
        try:
            bucket = self.storage_client.bucket(self.gcs_bucket_name)
            prefix = f"{self.job.id}/"
            blobs = list(bucket.list_blobs(prefix=prefix))
            if blobs:
                self.update_progress(3, 3, f"A limpar {len(blobs)} arquivos...", extra_info={'cleanup': True})
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    executor.map(lambda blob: blob.delete(), blobs)
        except Exception:
            pass

    def process_document_batch_fast(self, pdf_path, page_range):
        if not self.gcs_bucket_name: raise ValueError("Bucket do GCS não configurado.")
        try:
            reader = PdfReader(pdf_path, strict=False)
            total_pdf_pages = len(reader.pages)
        except PdfReadError as e:
            raise ValueError(f"PDF corrompido: {e}")

        page_indices = []
        if page_range:
            parts = page_range.split('-')
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                start_page = int(parts[0]) - 1
                end_page = int(parts[1])
                page_indices = list(range(start_page, min(end_page, total_pdf_pages)))
            elif len(parts) == 1 and parts[0].isdigit():
                page_num = int(parts[0]) - 1
                if 0 <= page_num < total_pdf_pages: page_indices = [page_num]
        else:
            page_indices = list(range(total_pdf_pages))

        if not page_indices: 
            raise ValueError("Nenhuma página válida para processar.")
        
        total_pages_to_process = len(page_indices)
        self.upload_counter = 0
        self.update_progress(0, 3, f"A iniciar upload de {total_pages_to_process} páginas...", extra_info={'upload_progress': 0, 'upload_total': total_pages_to_process})
        
        gcs_documents = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(self.upload_page_to_gcs, reader, page_idx, idx, total_pages_to_process): idx for idx, page_idx in enumerate(page_indices)}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result and result[0] is not None:
                    gcs_documents.append(result)
        
        if not gcs_documents: 
            raise ValueError("Nenhuma página foi carregada.")
        
        gcs_documents.sort(key=lambda x: x[0])
        gcs_documents = [doc for _, doc in gcs_documents]

        client = documentai.DocumentProcessorServiceClient(client_options={"api_endpoint": f"{self.location}-documentai.googleapis.com"})
        output_config = documentai.DocumentOutputConfig(gcs_output_config={"gcs_uri": f"gs://{self.gcs_bucket_name}/{self.job.id}/output"})
        input_config = documentai.BatchDocumentsInputConfig(gcs_documents=documentai.GcsDocuments(documents=gcs_documents))
        request = documentai.BatchProcessRequest(name=client.processor_path(self.project_id, self.location, self.processor_id), input_documents=input_config, document_output_config=output_config)
        
        self.update_progress(1, 3, f"A processar {len(gcs_documents)} páginas pela IA...", extra_info={'ai_processing': True, 'ai_total_pages': len(gcs_documents), 'ai_message': f"Aguardando IA..."})
        operation = client.batch_process_documents(request)
        operation.result(timeout=3600)

        self.download_counter = 0
        self.update_progress(2, 3, "A recolher resultados...", extra_info={'download_progress': 0, 'download_total': len(gcs_documents)})
        
        bucket = self.storage_client.bucket(self.gcs_bucket_name)
        output_blobs = list(bucket.list_blobs(prefix=f"{self.job.id}/output/"))
        
        pages_data = {}
        def download_and_parse(blob):
            try:
                doc_proto = documentai.Document.from_json(blob.download_as_bytes())
                match = re.search(r'page_(\d+)', blob.name)
                if match:
                    page_num = int(match.group(1))
                    with self.download_lock:
                        self.download_counter += 1
                        self.update_progress(2, 3, "A recolher resultados...", extra_info={'download_progress': self.download_counter, 'download_total': len(gcs_documents), 'download_message': f"Download: {self.download_counter}/{len(gcs_documents)}"})
                    return page_num, {'entities': doc_proto.entities}
            except Exception:
                return None, None

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            for page_num, data in executor.map(download_and_parse, output_blobs):
                if page_num is not None: pages_data[page_num] = data
        
        return pages_data

    def format_ai_rows_by_order(self, entities):
        extracted_rows = []
        
        def clean_time(time_str):
            if not time_str:
                return '0'
            match = re.search(r'(\d{2}:\d{2})', time_str)
            return match.group(1) if match else '0'
        
        for entity in entities:
            if entity.type_.lower() == 'tabela_marcacoes' and entity.properties:
                row_data = {prop.type_.lower(): prop.mention_text.strip() for prop in entity.properties}
                
                extracted_rows.append({
                    'Dia': row_data.get('data', '0'),
                    'Dia_Sema': row_data.get('dia_semana', '0').lower(),
                    'Entrada1': clean_time(row_data.get('entrada1', '0')),
                    'Saida1': clean_time(row_data.get('saida1', '0')),
                    'Entrada2': clean_time(row_data.get('entrada2', '0')),
                    'Saida2': clean_time(row_data.get('saida2', '0')),
                    'Entrada3': clean_time(row_data.get('entrada3', '0')),
                    'Saida3': clean_time(row_data.get('saida3', '0')),
                    'Entrada4': clean_time(row_data.get('entrada4', '0')),
                    'Saida4': clean_time(row_data.get('saida4', '0')),
                })
        
        return extracted_rows

def parse_flexible_date(date_str):
    for fmt in ('%d/%m/%Y', '%d/%m/%y'):
        try:
            return pd.to_datetime(date_str, format=fmt)
        except (ValueError, TypeError):
            pass
    return pd.NaT

def process_pdf_task(pdf_path, pages, model_type, user_id):
    job = get_current_job()
    if not job: 
        return None

    job.meta['user_id'] = user_id
    job.save_meta()

    extractor = ExtractorGeral(model_type, job)
    try:
        pages_data = extractor.process_document_batch_fast(pdf_path, pages)
        
        extractor.update_progress(2, 3, "A consolidar dados...", extra_info={'consolidating': True})
        
        all_rows = []
        for page_order in sorted(pages_data.keys()):
            if pages_data[page_order] and pages_data[page_order]['entities']:
                ai_rows = extractor.format_ai_rows_by_order(pages_data[page_order]['entities'])
                all_rows.extend(ai_rows)

        if not all_rows:
            raise Exception("Nenhuma linha foi extraída pela IA.")
        
        full_final_df = pd.DataFrame(all_rows)
        
        full_final_df['Dia_dt'] = full_final_df['Dia'].apply(parse_flexible_date)
        
        full_final_df = full_final_df.dropna(subset=['Dia_dt'])
        full_final_df = full_final_df.sort_values(by='Dia_dt', ascending=True)
        
        full_final_df['Dia'] = full_final_df['Dia_dt'].dt.strftime('%d/%m/%Y')
        
        colunas_finais = ['Dia', 'Dia_Sema', 'Entrada1', 'Saida1', 'Entrada2', 'Saida2', 'Entrada3', 'Saida3', 'Entrada4', 'Saida4']
        
        for col in colunas_finais:
            if col not in full_final_df.columns:
                full_final_df[col] = "0"
        
        final_df = full_final_df[colunas_finais].fillna("0")
        
        output = BytesIO()
        final_df.to_csv(output, index=False, sep=';', encoding='utf-8-sig')
        output.seek(0)
        filename = f'Ponto_IA_extraido_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        temp_file_path = os.path.join(tempfile.gettempdir(), f"{job.id}.csv")
        with open(temp_file_path, 'wb') as f: f.write(output.getvalue())

        extractor.cleanup_gcs_files()
        
        extractor.update_progress(3, 3, "Processamento concluído!", status='completed')
        job.meta.update({'status': 'completed', 'file_path': temp_file_path, 'filename': filename})
        job.save()

        return temp_file_path
        
    except Exception as e:
        error_message = f'Erro no processamento principal: {str(e)}'
        traceback.print_exc()
        try: 
            extractor.cleanup_gcs_files()
        except Exception:
            pass
        job.meta.update({'status': 'error', 'error': error_message})
        job.save()
        return None
    finally:
        if os.path.exists(pdf_path):
            try:
                os.unlink(pdf_path)
            except Exception:
                pass
