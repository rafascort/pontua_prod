# /opt/pontua/AutoPonto/backend_api/extractor_geral_ai.py
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
    def __init__(self, model_type='6', job=None):
        self.model_type = model_type
        self.job = job
        self.project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
        self.location = os.getenv('DOCAI_PROCESSOR_LOCATION')
        self.processor_id = os.getenv('DOCAI_PROCESSOR_ID')
        self.gcs_bucket_name = os.getenv('GCS_BUCKET_NAME')
        self.storage_client = storage.Client()
        self.upload_counter = 0
        self.upload_lock = threading.Lock()
        print(f"[LOG] Instância do ExtractorGeralAI criada para o Job ID: {self.job.id if self.job else 'N/A'}")

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
            writer = PdfWriter(); writer.add_page(reader.pages[page_idx])
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                writer.write(tmp_file); single_page_path = tmp_file.name
            try:
                bucket = self.storage_client.bucket(self.gcs_bucket_name)
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
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    executor.map(lambda blob: blob.delete(), blobs)
        except Exception as e:
            print(f"⚠️ Erro ao limpar bucket: {e}")

    def process_document_batch_fast(self, pdf_path, pages_with_periods):
        if not self.gcs_bucket_name: raise ValueError("Bucket do GCS não configurado.")
        try:
            reader = PdfReader(pdf_path, strict=False)
        except PdfReadError as e:
            raise ValueError(f"PDF corrompido: {e}")

        page_indices = [p['page_index'] for p in pages_with_periods]
        total_pages = len(page_indices)
        self.upload_counter = 0
        self.update_progress(0, 3, f"Iniciando upload de {total_pages} páginas...", extra_info={'upload_progress': 0, 'upload_total': total_pages})

        gcs_documents = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(self.upload_page_to_gcs, reader, page_idx, idx, total_pages): idx for idx, page_idx in enumerate(page_indices)}
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result and result[0] is not None:
                    gcs_documents.append(result)

        if not gcs_documents: raise ValueError("Nenhuma página foi carregada com sucesso.")
        
        gcs_documents.sort(key=lambda x: x[0])
        gcs_documents_final = [doc for _, doc in gcs_documents]

        # --- NOVA LÓGICA DE PROCESSAMENTO SEQUENCIAL ---
        client = documentai.DocumentProcessorServiceClient(client_options={"api_endpoint": f"{self.location}-documentai.googleapis.com"})
        processor_name = client.processor_path(self.project_id, self.location, self.processor_id)
        
        pages_data = {}
        total_ai_pages = len(gcs_documents_final)

        for idx, gcs_doc in enumerate(gcs_documents_final):
            self.update_progress(1, 3, f"A processar página {idx + 1} de {total_ai_pages} pela IA...", extra_info={
                'ai_processing': True,
                'ai_total_pages': total_ai_pages,
                'ai_current_page': idx + 1,
                'ai_message': f"A processar {idx + 1}/{total_ai_pages} páginas pela IA..."
            })

            try:
                request = documentai.ProcessRequest(name=processor_name, gcs_document=gcs_doc)
                result = client.process_document(request=request)
                document = result.document
                pages_data[idx] = {'entities': document.entities}
            except Exception as e:
                print(f"⚠️ Erro ao processar página {idx} com Document AI: {e}")
                pages_data[idx] = {'entities': []} # Continua mesmo se uma página falhar

        self.update_progress(2, 3, "Recolhendo e consolidando resultados...", extra_info={'consolidating': True})
        # --- FIM DA NOVA LÓGICA ---

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
    
    print(f"\n[LOG][Job {job.id}] INICIANDO TAREFA: extract_periods_task")
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

def process_pdf_task(pdf_path, pages_with_periods_json, model_type, user_id):
    job = get_current_job()
    if not job: return None

    print(f"\n[LOG][Job {job.id}] INICIANDO TAREFA: process_pdf_task (IA)")
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
        
        extractor.update_progress(2, 3, "A consolidar dados...", extra_info={'consolidating': True})
        
        all_page_dataframes = []
        for idx, page_info in enumerate(pages_with_periods):
            page_order, page_num = idx, page_info['page_index']
            if 'start_date_obj' not in page_info: continue
            start_date, end_date = page_info['start_date_obj'], page_info['end_date_obj']
            
            full_date_range = pd.date_range(start=start_date, end=end_date, freq='D')
            calendar_df = pd.DataFrame(full_date_range, columns=['Dia_dt'])
            calendar_df['original_page'] = page_num + 1

            if page_order not in pages_data or not pages_data.get(page_order, {}).get('entities'):
                print(f"[LOG][Job {job.id}] Aviso: Nenhum dado da IA para pág {page_num + 1}. Página ficará zerada.")
                all_page_dataframes.append(calendar_df)
                continue
            
            ai_rows = extractor.format_ai_rows_by_order(pages_data[page_order]['entities'])
            ai_data_df = pd.DataFrame(ai_rows)
            print(f"[LOG][Job {job.id}] Pág {page_num + 1}: Calendário tem {len(calendar_df)} dias. IA extraiu {len(ai_data_df)} linhas.")

            calendar_df.reset_index(drop=True, inplace=True)
            ai_data_df.reset_index(drop=True, inplace=True)
            
            period_df = pd.concat([calendar_df, ai_data_df], axis=1)
            all_page_dataframes.append(period_df)

        if not all_page_dataframes:
            raise Exception("Nenhum DataFrame de página foi gerado.")

        print(f"[LOG][Job {job.id}] Consolidando e ordenando dados de todas as páginas.")
        
        full_final_df = pd.concat(all_page_dataframes, ignore_index=True)
        full_final_df = full_final_df.sort_values('Dia_dt').drop_duplicates(subset=['Dia_dt'], keep='last')
        
        min_date_overall = full_final_df['Dia_dt'].min()
        max_date_overall = full_final_df['Dia_dt'].max()
        overall_date_range = pd.date_range(start=min_date_overall, end=max_date_overall, freq='D')
        
        final_df = full_final_df.set_index('Dia_dt').reindex(overall_date_range).reset_index()
        final_df.rename(columns={'index': 'Dia_dt'}, inplace=True)

        final_df['Dia'] = final_df['Dia_dt'].dt.strftime('%d/%m/%Y')
        day_map_pt = {0: "seg", 1: "ter", 2: "qua", 3: "qui", 4: "sex", 5: "sab", 6: "dom"}
        final_df['Dia_Sema'] = final_df['Dia_dt'].dt.dayofweek.map(day_map_pt)
        
        final_df.rename(columns={'entrada1': 'Entrada1', 'saida1': 'Saida1', 'entrada2': 'Entrada2', 'saida2': 'Saida2', 'entrada3': 'Entrada3', 'saida3': 'Saida3'}, inplace=True)
        
        colunas_finais = ['Dia', 'Dia_Sema', 'Entrada1', 'Saida1', 'Entrada2', 'Saida2', 'Entrada3', 'Saida3']
        for col in colunas_finais:
            if col not in final_df.columns:
                final_df[col] = "0"
        
        final_df = final_df[colunas_finais].fillna("0")
        
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

        print(f"[LOG][Job {job.id}] SUCESSO: Tarefa process_pdf_task concluída.")
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
