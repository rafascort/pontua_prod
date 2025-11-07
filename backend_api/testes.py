# /opt/pontua/AutoPonto/backend_api/testes.py
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

from pdf2image import convert_from_path
import pytesseract
import platform

if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'


class ExtractorGeralAI:
    def __init__(self, model_type='8', job=None): # Model type '8' (teste)
        self.model_type = model_type
        self.job = job
        self.project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        self.location = os.getenv('DOCAI_PROCESSOR_LOCATION')
        self.processor_id = os.getenv('DOCAI_PROCESSOR_ID')
        self.gcs_bucket_name = os.getenv('GCS_BUCKET_NAME')
        self.storage_client = storage.Client()
        self.upload_counter = 0
        self.upload_lock = threading.Lock()
        print(f"[LOG] Instância do ExtractorGeralAI (TESTE API) criada para o Job ID: {self.job.id if self.job else 'N/A'}")

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
            print(f"[LOG][Job {self.job.id}] Progresso: {progress}% - {message}")

    def extract_period_from_page(self, pdf_path, page_idx):
        try:
            images = convert_from_path(pdf_path, dpi=300, first_page=page_idx + 1, last_page=page_idx + 1)
            if not images: return None
            
            image = images[0]
            width, height = image.size
            top_section = image.crop((0, 0, width, height * 0.3)) 
            
            config_ocr_header = r'--oem 3 --psm 6 -l por'
            text = pytesseract.image_to_string(top_section, lang='por', config=config_ocr_header)
            
            if not text: return None

            for line in text.splitlines():
                dates_found = re.findall(r'\b(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\b', line)
                if len(dates_found) >= 2:
                    try:
                        start_date_str = dates_found[0].replace('.', '/').replace('-', '/')
                        end_date_str = dates_found[1].replace('.', '/').replace('-', '/')
                        
                        try:
                            start_date = datetime.strptime(start_date_str, '%d/%m/%Y')
                            end_date = datetime.strptime(end_date_str, '%d/%m/%Y')
                        except ValueError:
                            start_date = datetime.strptime(start_date_str, '%d/%m/%y')
                            end_date = datetime.strptime(end_date_str, '%d/%m/%y')

                        return {
                            'start_date': start_date.strftime('%d/%m/%Y'),
                            'end_date': end_date.strftime('%d/%m/%Y'),
                        }
                    except ValueError:
                        continue
            return None
        except Exception as e:
            print(f"[LOG][ERRO] Erro crítico ao extrair período da página {page_idx + 1}: {e}")
            return None

    def split_pdf_and_extract_periods(self, pdf_path, page_range):
        try:
            reader = PdfReader(pdf_path, strict=False)
            total_pdf_pages = len(reader.pages)
        except PdfReadError as e:
            raise ValueError(f"PDF corrompido ou inválido: {str(e)}")
        
        page_indices = []
        if page_range:
            parts = page_range.split('-')
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                start_page = int(parts[0]) - 1; end_page = int(parts[1])
                page_indices = list(range(start_page, min(end_page, total_pdf_pages)))
            elif len(parts) == 1 and parts[0].isdigit():
                page_num = int(parts[0]) - 1
                if 0 <= page_num < total_pdf_pages: page_indices = [page_num]
        else:
            page_indices = list(range(total_pdf_pages))

        if not page_indices: raise ValueError("Nenhuma página válida para processar.")
        
        pages_info = []
        for idx, page_idx in enumerate(page_indices):
            self.update_progress(idx + 1, len(page_indices), f"Lendo cabeçalho da página {page_idx + 1} com OCR...", status='processing')
            period = self.extract_period_from_page(pdf_path, page_idx)
            pages_info.append({'page_number': page_idx + 1, 'page_index': page_idx, 'period': period})
        
        return pages_info

    def upload_page_to_gcs(self, reader, page_idx, idx, total_pages):
        try:
            if page_idx >= len(reader.pages):
                print(f"⚠️ Erro ao processar/upload da página {page_idx + 1}: Índice de página ({page_idx}) está fora do alcance. O PDF pode ter apenas {len(reader.pages)} páginas.")
                return None, None
            writer = PdfWriter(); writer.add_page(reader.pages[page_idx])
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                writer.write(tmp_file); single_page_path = tmp_file.name
            try:
                bucket = self.storage_client.bucket(self.gcs_bucket_name)
                # O nome do blob usa 'idx' (0, 1, 2...) para facilitar o mapeamento
                blob_name = f"{self.job.id}/input/page_{idx:05d}.pdf"
                gcs_input_uri = f"gs://{self.gcs_bucket_name}/{blob_name}"
                bucket.blob(blob_name).upload_from_filename(single_page_path)
                with self.upload_lock:
                    self.upload_counter += 1
                    self.update_progress(0, 3, "Subindo páginas para análise...", extra_info={'upload_progress': self.upload_counter, 'upload_total': total_pages, 'upload_message': f"Upload: {self.upload_counter}/{total_pages} páginas"})
                return idx, documentai.GcsDocument(gcs_uri=gcs_input_uri, mime_type="application/pdf")
            finally:
                if os.path.exists(single_page_path): os.unlink(single_page_path)
        except Exception as e:
            print(f"⚠️ Erro ao processar/upload da página {page_idx + 1}: {e}")
            return None, None

    def cleanup_gcs_files(self):
        try:
            bucket = self.storage_client.bucket(self.gcs_bucket_name)
            prefix = f"{self.job.id}/"
            blobs = list(bucket.list_blobs(prefix=prefix))
            if blobs:
                self.update_progress(3, 3, f"Limpando {len(blobs)} arquivos temporários...", extra_info={'cleanup': True})
                # Otimização: Apagar em lote
                with self.storage_client.batch():
                    for blob in blobs:
                        blob.delete()
        except Exception as e:
            print(f"⚠️ Erro ao limpar bucket: {e}")

    # --- FUNÇÃO ATUALIZADA (LÓGICA DE BATCH) ---
    def process_document_batch_fast(self, pdf_path, pages_with_periods):
        if not self.gcs_bucket_name:
            raise ValueError("Bucket do GCS não configurado.")
        try:
            reader = PdfReader(pdf_path, strict=False)
        except (PdfReadError, Exception) as e:
            raise ValueError(f"PDF corrompido ou ilegível: {e}")
        
        page_indices = [p['page_index'] for p in pages_with_periods]
        total_pages = len(page_indices)
        self.upload_counter = 0
        self.update_progress(0, 3, f"Iniciando upload de {total_pages} páginas...", extra_info={'upload_progress': 0, 'upload_total': total_pages})
        
        gcs_documents_with_index = []
        
        for idx, page_idx in enumerate(page_indices):
            result_idx, gcs_doc = self.upload_page_to_gcs(reader, page_idx, idx, total_pages)
            if gcs_doc:
                gcs_documents_with_index.append((result_idx, gcs_doc))

        if not gcs_documents_with_index:
            raise ValueError("Nenhuma página pôde ser carregada. Verifique o arquivo PDF.")
        
        gcs_documents_with_index.sort(key=lambda x: x[0])
        gcs_documents_final = [doc for _, doc in gcs_documents_with_index]
        original_indices = [idx for idx, _ in gcs_documents_with_index] 

        self.update_progress(1, 3, f"Enviando {len(gcs_documents_final)} páginas para processamento em lote...", extra_info={'ai_processing': True, 'ai_total_pages': len(gcs_documents_final), 'ai_current_page': 0, 'ai_message': 'Iniciando processamento em lote...'})
        
        client = documentai.DocumentProcessorServiceClient(client_options={"api_endpoint": f"{self.location}-documentai.googleapis.com"})
        
        gcs_documents_wrapper = documentai.GcsDocuments(documents=gcs_documents_final)
        
        output_config = documentai.DocumentOutputConfig(
            gcs_output_config={"gcs_uri": f"gs://{self.gcs_bucket_name}/{self.job.id}/output/"}
        )
        input_config = documentai.BatchDocumentsInputConfig(
            gcs_documents=gcs_documents_wrapper
        )
        request = documentai.BatchProcessRequest(
            name=client.processor_path(self.project_id, self.location, self.processor_id),
            input_documents=input_config,
            document_output_config=output_config
        )

        operation = client.batch_process_documents(request)
        print(f"[LOG][Job {self.job.id}] Operação de lote (TESTE API) iniciada. Aguardando resultado...")
        
        try:
             operation.result(timeout=3600) 
        except Exception as batch_err:
             print(f"⚠️ Erro durante a operação de lote (operação pode ter falhado parcialmente): {batch_err}")
        
        print(f"[LOG][Job {self.job.id}] Operação de lote (TESTE API) concluída. Coletando resultados.")
        self.update_progress(2, 3, "A recolher e consolidar resultados...", extra_info={'consolidating': True})
        
        bucket = self.storage_client.bucket(self.gcs_bucket_name)
        output_blobs = list(bucket.list_blobs(prefix=f"{self.job.id}/output/"))
        
        if not output_blobs:
            raise Exception("O processamento da IA (em lote) não gerou arquivos de saída.")
        
        pages_data = {}
        processed_count = 0
        total_ai_pages = len(gcs_documents_final)

        blob_name_regex = re.compile(r'/(\d+)\.json$')

        for blob in output_blobs:
            match = blob_name_regex.search(blob.name)
            if not match:
                print(f"[LOG][Job {self.job.id}] Aviso: Ignorando arquivo de saída não esperado: {blob.name}")
                continue
                
            try:
                original_doc_index = int(match.group(1)) 
                
                if original_doc_index < len(original_indices):
                    page_key = original_indices[original_doc_index] 
                    
                    doc_proto = documentai.Document.from_json(blob.download_as_bytes())
                    pages_data[page_key] = {'entities': doc_proto.entities}
                    processed_count += 1
                    
                    self.update_progress(2, 3, "A recolher e consolidar resultados...", extra_info={
                        'ai_processing': False,
                        'consolidating': True,
                        'ai_total_pages': total_ai_pages,
                        'ai_current_page': processed_count,
                        'ai_message': f"A consolidar {processed_count}/{total_ai_pages} resultados..."
                    })
                else:
                    print(f"[LOG][Job {self.job.id}] Aviso: Índice de blob '{original_doc_index}' fora do intervalo de índices esperados.")
                    
            except Exception as e:
                print(f"⚠️ Erro ao processar blob {blob.name}: {e}")
                
        if not pages_data:
             raise Exception("Processamento em lote concluído, mas nenhum resultado de entidade foi lido com sucesso.")

        print(f"[LOG][Job {self.job.id}] Consolidação concluída. {len(pages_data)} páginas processadas.")
        return pages_data

    def format_ai_rows_by_order(self, entities):
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
    
def extract_periods_task(pdf_path, pages, user_id):
    job = get_current_job()
    if not job: 
        print("[LOG][ERRO] FATAL: Não foi possível obter o objeto job do RQ na tarefa de extração de períodos.")
        return None
    
    print(f"\n[LOG][Job {job.id}] INICIANDO TAREFA: extract_periods_task (TESTE API)")
    job.meta['user_id'] = user_id; job.save_meta()
    
    extractor = ExtractorGeralAI(job=job)
    try:
        pages_info = extractor.split_pdf_and_extract_periods(pdf_path, pages)
        
        job.meta.update({'status': 'completed', 'result': pages_info, 'pdf_path': pdf_path}); job.save()
        print(f"[LOG][Job {job.id}] SUCESSO: Tarefa extract_periods_task concluída.")
        return pages_info
    except Exception as e:
        error_message = f'Erro ao extrair períodos: {str(e)}'
        print(f"[LOG][ERRO][Job {job.id}] {error_message}\n{traceback.format_exc()}")
        job.meta.update({'status': 'error', 'error': str(e)}); job.save()
        return None

def normalize_time_format(value):
    if pd.isna(value) or value == "0" or value == 0 or value == "":
        return "0"
    
    value_str = str(value).strip()
    
    if value_str == "0" or value_str == "":
        return "0"
    
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

def process_pdf_task(pdf_path, pages_with_periods_json, model_type, user_id):
    job = get_current_job()
    if not job: return None

    print(f"\n[LOG][Job {job.id}] INICIANDO TAREFA: process_pdf_task (TESTE API)")
    job.meta['user_id'] = user_id; job.save_meta()

    pages_with_periods = []
    for p in pages_with_periods_json:
        if p.get('period') and p['period'].get('start_date') and p['period'].get('end_date'):
            try:
                p['start_date_obj'] = datetime.strptime(p['period']['start_date'], '%d/%m/%Y')
                p['end_date_obj'] = datetime.strptime(p['period']['end_date'], '%d/%m/%Y')
                pages_with_periods.append(p)
            except (ValueError, TypeError):
                print(f"[LOG][Job {job.id}] Aviso: Período inválido ignorado para pág {p.get('page_number')}")

    if not pages_with_periods:
        job.meta.update({'status': 'error', 'error': 'Nenhuma página com período válido fornecida.'}); job.save()
        return None

    extractor = ExtractorGeralAI(model_type, job)
    try:
        pages_data = extractor.process_document_batch_fast(pdf_path, pages_with_periods)
        
        extractor.update_progress(2, 3, "A consolidar dados...", extra_info={'consolidating': True, 'ai_processing': False})
        
        all_page_dataframes = []
        for idx, page_info in enumerate(pages_with_periods):
            page_order, page_num = idx, page_info['page_index']
            if 'start_date_obj' not in page_info:
                print(f"[LOG][Job {job.id}] Aviso: Período inválido ou ausente para pág {page_num + 1}. Pulando.")
                continue
                
            start_date, end_date = page_info['start_date_obj'], page_info['end_date_obj']
            
            full_date_range = pd.date_range(start=start_date, end=end_date, freq='D')
            calendar_df = pd.DataFrame(full_date_range, columns=['Dia_dt'])
            calendar_df['original_page'] = page_num + 1
            
            print(f"[LOG][Job {job.id}] Pág {page_num + 1}: Calendário criado com {len(calendar_df)} dias.")

            if page_order not in pages_data or not pages_data.get(page_order, {}).get('entities'):
                print(f"[LOG][Job {job.id}] Aviso: Nenhum dado da IA para pág {page_num + 1} (Índice {page_order}). Página ficará zerada.")
                all_page_dataframes.append(calendar_df)
                continue
            
            ai_rows = extractor.format_ai_rows_by_order(pages_data[page_order]['entities'])
            ai_data_df = pd.DataFrame(ai_rows)
            print(f"[LOG][Job {job.id}] Pág {page_num + 1}: IA extraiu {len(ai_data_df)} linhas de marcações.")

            calendar_df.reset_index(drop=True, inplace=True)
            ai_data_df.reset_index(drop=True, inplace=True)
            
            period_df = pd.concat([calendar_df, ai_data_df], axis=1)
            all_page_dataframes.append(period_df)

        if not all_page_dataframes:
            raise Exception("Nenhum DataFrame de página foi gerado.")

        print(f"[LOG][Job {job.id}] Consolidando e ordenando dados de todas as páginas.")
        
        full_final_df = pd.concat(all_page_dataframes, ignore_index=True)
        
        if 'Dia_dt' not in full_final_df.columns or full_final_df['Dia_dt'].isnull().all():
            raise ValueError("Não foi possível determinar um intervalo de datas válido a partir dos dados processados.")

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
        
        print(f"[LOG][Job {job.id}] 🔍 Iniciando validação e correção de formato de horários...")
        
        time_columns = ['Entrada1', 'Saida1', 'Entrada2', 'Saida2', 'Entrada3', 'Saida3']
        
        for col in time_columns:
            if col in final_df.columns:
                final_df[col] = final_df[col].apply(normalize_time_format)
        
        print(f"[LOG][Job {job.id}] DataFrame final criado com {len(final_df)} linhas. Gerando CSV.")
        
        output = BytesIO()
        final_df.to_csv(output, index=False, sep=';', encoding='utf-8-sig')
        output.seek(0)
        filename = f'Ponto_IA_extraido_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        temp_file_path = os.path.join(tempfile.gettempdir(), f"{job.id}.csv")
        with open(temp_file_path, 'wb') as f: f.write(output.getvalue())

        print(f"[LOG][Job {job.id}] CSV gerado. Limpando arquivos do GCS.")
        extractor.cleanup_gcs_files()
        
        extractor.update_progress(3, 3, "Processamento concluído!", status='completed')
        job.meta.update({'status': 'completed', 'file_path': temp_file_path, 'filename': filename})
        job.save()

        print(f"[LOG][Job {job.id}] SUCESSO: Tarefa process_pdf_task (TESTE API) concluída.")
        return temp_file_path
        
    except Exception as e:
        error_message = f'Erro no processamento principal: {str(e)}'
        print(f"[LOG][ERRO][Job {job.id}] {error_message}\n{traceback.format_exc()}")
        try: extractor.cleanup_gcs_files()
        except: pass
        job.meta.update({'status': 'error', 'error': error_message})
        job.save()
        return None
    finally:
        if os.path.exists(pdf_path):
            try:
                os.unlink(pdf_path)
            except Exception as e:
                print(f"[LOG][ERRO][Job {job.id}] Falha ao remover PDF temporário {pdf_path}: {e}")
