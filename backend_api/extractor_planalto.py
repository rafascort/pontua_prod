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

class ExtractorPlanaltoAI:
    def __init__(self, model_type='5', job=None):
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
                'progress': progress,
                'message': message,
                'current_step': current,
                'total_steps': total,
                'status': status,
                'timestamp': datetime.now().isoformat()
            }
            if extra_info:
                meta_update.update(extra_info)
            self.job.meta.update(meta_update)
            self.job.save_meta()

    def extract_period_from_page(self, pdf_path, page_idx):
        """Extrai o período de uma página específica do PDF"""
        try:
            reader = PdfReader(pdf_path, strict=False)
            
            if page_idx >= len(reader.pages):
                return None
            
            page = reader.pages[page_idx]
            text = page.extract_text()
            
            # Procura por padrão: PERIODO DE: DD/MM/YYYY A DD/MM/YYYY
            match = re.search(r'PERIODO\s+DE[:\s]*(\d{2}/\d{2}/\d{4})\s+A\s+(\d{2}/\d{2}/\d{4})', text, re.IGNORECASE)
            if match:
                try:
                    start_date = datetime.strptime(match.group(1), '%d/%m/%Y')
                    end_date = datetime.strptime(match.group(2), '%d/%m/%Y')
                    return {
                        'start_date': start_date.strftime('%d/%m/%Y'),
                        'end_date': end_date.strftime('%d/%m/%Y'),
                        'start_date_obj': start_date,
                        'end_date_obj': end_date
                    }
                except ValueError:
                    pass
            
            # Fallback: procura apenas uma data
            match = re.search(r'PERIODO\s+DE[:\s]*(\d{2}/\d{2}/\d{4})', text, re.IGNORECASE)
            if match:
                try:
                    date = datetime.strptime(match.group(1), '%d/%m/%Y')
                    return {
                        'start_date': date.strftime('%d/%m/%Y'),
                        'end_date': date.strftime('%d/%m/%Y'),
                        'start_date_obj': date,
                        'end_date_obj': date
                    }
                except ValueError:
                    pass
                    
            return None
        except Exception as e:
            print(f"⚠️ Erro ao extrair período da página {page_idx + 1}: {e}")
            return None

    def split_pdf_and_extract_periods(self, pdf_path, page_range):
        """Divide o PDF e extrai os períodos de cada página"""
        try:
            reader = PdfReader(pdf_path, strict=False)
            total_pdf_pages = len(reader.pages)
        except PdfReadError as e:
            raise ValueError(f"PDF corrompido ou inválido: {str(e)}")
        
        # Parse do range de páginas
        page_indices = []
        if page_range:
            parts = page_range.split('-')
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                start_page = int(parts[0]) - 1
                end_page = int(parts[1])
                
                if start_page >= total_pdf_pages:
                    raise ValueError(f"O PDF tem apenas {total_pdf_pages} páginas. Você pediu a partir da página {parts[0]}.")
                
                end_page = min(end_page, total_pdf_pages)
                page_indices = list(range(start_page, end_page))
                
            elif len(parts) == 1 and parts[0].isdigit():
                page_num = int(parts[0]) - 1
                if page_num >= total_pdf_pages:
                    raise ValueError(f"O PDF tem apenas {total_pdf_pages} páginas. Você pediu página {parts[0]}.")
                page_indices = [page_num]
        else:
            page_indices = list(range(total_pdf_pages))

        page_indices = [idx for idx in page_indices if 0 <= idx < total_pdf_pages]
        
        if not page_indices:
            raise ValueError("Nenhuma página válida para processar.")
        
        self.update_progress(
            0, 1,
            f"A extrair períodos de {len(page_indices)} páginas...",
            status='extracting_periods'
        )
        
        # Extrai períodos de todas as páginas
        pages_info = []
        for idx, page_idx in enumerate(page_indices):
            period = self.extract_period_from_page(pdf_path, page_idx)
            pages_info.append({
                'page_number': page_idx + 1,
                'page_index': page_idx,
                'period': period
            })
            
            self.update_progress(
                idx + 1, len(page_indices),
                f"Extraindo períodos: {idx + 1}/{len(page_indices)} páginas",
                status='extracting_periods',
                extra_info={'pages_processed': idx + 1, 'total_pages': len(page_indices)}
            )
        
        return pages_info

    def upload_page_to_gcs(self, reader, page_idx, idx, total_pages):
        """Upload de uma página para GCS (executado em paralelo)"""
        try:
            writer = PdfWriter()
            
            if page_idx >= len(reader.pages):
                print(f"⚠️ Página {page_idx + 1} não existe (PDF tem {len(reader.pages)} páginas)")
                return None, None
            
            try:
                writer.add_page(reader.pages[page_idx])
            except (PdfReadError, IndexError) as e:
                print(f"⚠️ Erro ao ler página {page_idx + 1}: {e}")
                return None, None
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                writer.write(tmp_file)
                single_page_path = tmp_file.name

            try:
                bucket = self.storage_client.bucket(self.gcs_bucket_name)
                blob_name = f"{self.job.id}/input/page_{idx:05d}.pdf"
                gcs_input_uri = f"gs://{self.gcs_bucket_name}/{blob_name}"
                blob = bucket.blob(blob_name)
                blob.upload_from_filename(single_page_path)

                with self.upload_lock:
                    self.upload_counter += 1
                    self.update_progress(
                        0, 3,
                        f"A fazer upload das páginas para processamento...",
                        extra_info={
                            'upload_progress': self.upload_counter,
                            'upload_total': total_pages,
                            'upload_message': f"Upload: {self.upload_counter}/{total_pages} páginas"
                        }
                    )

                return idx, documentai.GcsDocument(
                    gcs_uri=gcs_input_uri,
                    mime_type="application/pdf"
                )
            finally:
                if os.path.exists(single_page_path):
                    os.unlink(single_page_path)
        except Exception as e:
            print(f"⚠️ Erro fatal ao processar página {page_idx + 1}: {e}")
            return None, None

    def cleanup_gcs_files(self):
        """Apaga todos os arquivos do job no bucket GCS"""
        try:
            bucket = self.storage_client.bucket(self.gcs_bucket_name)
            prefix = f"{self.job.id}/"
            
            blobs = list(bucket.list_blobs(prefix=prefix))
            
            if blobs:
                self.update_progress(
                    3, 3,
                    f"A limpar {len(blobs)} arquivos temporários do bucket...",
                    extra_info={'cleanup': True}
                )
                
                def delete_blob(blob):
                    try:
                        blob.delete()
                    except Exception as e:
                        print(f"Erro ao apagar {blob.name}: {e}")
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    executor.map(delete_blob, blobs)
                
                print(f"✅ {len(blobs)} arquivos apagados do bucket (job {self.job.id})")
        except Exception as e:
            print(f"⚠️ Erro ao limpar bucket: {e}")

    def process_document_batch_fast(self, pdf_path, pages_with_periods):
        """Processa múltiplas páginas em batch com upload paralelo"""
        if not self.gcs_bucket_name:
            raise ValueError("O nome do bucket do Google Cloud Storage não está configurado.")

        try:
            reader = PdfReader(pdf_path, strict=False)
        except PdfReadError as e:
            raise ValueError(f"PDF corrompido ou inválido: {e}")
        
        page_indices = [p['page_index'] for p in pages_with_periods]
        total_pages = len(page_indices)

        self.upload_counter = 0
        self.update_progress(
            0, 3,
            f"A iniciar upload de {total_pages} páginas...",
            extra_info={
                'upload_progress': 0,
                'upload_total': total_pages,
                'upload_message': f"Upload: 0/{total_pages} páginas"
            }
        )

        gcs_documents = []
        page_mapping = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(self.upload_page_to_gcs, reader, page_idx, idx, total_pages): idx 
                for idx, page_idx in enumerate(page_indices)
            }
            
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result[0] is not None:
                    idx, gcs_doc = result
                    gcs_documents.append((idx, gcs_doc))
                    page_mapping[f"page_{idx:05d}"] = idx

        if not gcs_documents:
            raise ValueError("Nenhuma página válida foi carregada. O PDF pode estar corrompido.")

        gcs_documents.sort(key=lambda x: x[0])
        gcs_documents = [doc for _, doc in gcs_documents]

        client = documentai.DocumentProcessorServiceClient(
            client_options={"api_endpoint": f"{self.location}-documentai.googleapis.com"}
        )

        gcs_output_uri = f"gs://{self.gcs_bucket_name}/{self.job.id}/output"
        output_config = documentai.DocumentOutputConfig(
            gcs_output_config={"gcs_uri": gcs_output_uri}
        )

        input_config = documentai.BatchDocumentsInputConfig(
            gcs_documents=documentai.GcsDocuments(documents=gcs_documents)
        )

        request = documentai.BatchProcessRequest(
            name=client.processor_path(self.project_id, self.location, self.processor_id),
            input_documents=input_config,
            document_output_config=output_config,
        )

        self.update_progress(
            1, 3,
            f"A processar {len(gcs_documents)} páginas válidas pela IA...",
            extra_info={
                'ai_processing': True,
                'ai_total_pages': len(gcs_documents),
                'ai_message': f"Aguardando processamento de {len(gcs_documents)} páginas pela IA (pode demorar 2-5 min)..."
            }
        )

        operation = client.batch_process_documents(request)
        operation.result(timeout=3600)

        self.download_counter = 0
        self.update_progress(
            2, 3,
            "A recolher resultados...",
            extra_info={
                'download_progress': 0,
                'download_total': len(gcs_documents),
                'download_message': f"Download: 0/{len(gcs_documents)} resultados"
            }
        )

        bucket = self.storage_client.bucket(self.gcs_bucket_name)
        output_blobs = list(bucket.list_blobs(prefix=f"{self.job.id}/output/"))

        pages_data = {}

        def download_and_parse(blob):
            try:
                json_bytes = blob.download_as_bytes()
                doc_proto = documentai.Document.from_json(json_bytes)
                
                match = re.search(r'page_(\d+)', blob.name)
                if match:
                    page_num = int(match.group(1))
                    
                    with self.download_lock:
                        self.download_counter += 1
                        self.update_progress(
                            2, 3,
                            "A recolher resultados...",
                            extra_info={
                                'download_progress': self.download_counter,
                                'download_total': len(gcs_documents),
                                'download_message': f"Download: {self.download_counter}/{len(gcs_documents)} resultados"
                            }
                        )
                    
                    return page_num, {
                        'entities': doc_proto.entities,
                        'text': doc_proto.text
                    }
            except Exception as e:
                print(f"⚠️ Erro ao processar resultado de {blob.name}: {e}")
            return None, None

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(download_and_parse, blob) for blob in output_blobs]
            for future in concurrent.futures.as_completed(futures):
                page_num, data = future.result()
                if page_num is not None:
                    pages_data[page_num] = data

        return pages_data

    def format_ai_data_to_rows(self, entities, start_date, end_date):
        """Converte entidades da IA em linhas de dados"""
        extracted_rows = []
        
        for entity in entities:
            if entity.type_ == 'tabela_marcacoes' and entity.properties:
                row_data = {}
                for prop in entity.properties:
                    row_data[prop.type_] = prop.mention_text.strip()

                day_val_str = row_data.get('data')
                if day_val_str:
                    full_date_obj = None
                    try:
                        if '/' in day_val_str:
                            full_date_obj = datetime.strptime(day_val_str, '%d/%m/%y')
                        elif len(day_val_str) == 6 and day_val_str.isdigit():
                            full_date_obj = datetime.strptime(day_val_str, '%d%m%y')
                        elif len(day_val_str) <= 2 and day_val_str.isdigit():
                            # Usa o dia extraído com mês/ano do período
                            day = int(day_val_str)
                            full_date_obj = datetime(start_date.year, start_date.month, day)
                            
                            # Verifica se a data está dentro do período
                            if full_date_obj < start_date:
                                # Tenta próximo mês
                                if start_date.month == 12:
                                    full_date_obj = datetime(start_date.year + 1, 1, day)
                                else:
                                    full_date_obj = datetime(start_date.year, start_date.month + 1, day)
                    except ValueError:
                        continue

                    if full_date_obj:
                        # Verifica se a data está dentro do período permitido
                        if start_date <= full_date_obj <= end_date:
                            row_data['Dia_dt'] = full_date_obj
                            extracted_rows.append(row_data)
        
        return extracted_rows


def extract_periods_task(pdf_path, pages, user_id, **kwargs):
    """Task para extrair períodos das páginas (PASSO 2)"""
    job = get_current_job()
    if not job:
        return None

    job.meta['user_id'] = user_id
    job.save_meta()

    extractor = ExtractorPlanaltoAI(job=job)

    try:
        pages_info = extractor.split_pdf_and_extract_periods(pdf_path, pages)
        
        job.meta.update({
            'status': 'periods_extracted',
            'pages_info': pages_info,
            'pdf_path': pdf_path
        })
        job.save()
        
        return pages_info

    except Exception as e:
        error_message = f'Erro ao extrair períodos: {str(e)}'
        print(error_message)
        
        job.meta.update({
            'status': 'error',
            'error': str(e)
        })
        job.save()
        
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)
        
        return None


def process_pdf_task(pdf_path, pages_with_periods, model_type, user_id, **kwargs):
    """Task para processar páginas confirmadas pelo usuário (PASSO 5)"""
    job = get_current_job()
    if not job:
        return None

    job.meta['user_id'] = user_id
    job.save_meta()

    extractor = ExtractorPlanaltoAI(model_type, job)

    try:
        extractor.update_progress(0, 3, "A preparar processamento...")
        
        # Processa todas as páginas simultaneamente
        pages_data = extractor.process_document_batch_fast(pdf_path, pages_with_periods)

        extractor.update_progress(
            2, 3,
            "A consolidar dados em ordem cronológica...",
            extra_info={'consolidating': True}
        )

        # Processa cada página e extrai os dados
        all_page_dataframes = []
        
        for idx, page_info in enumerate(pages_with_periods):
            page_order = idx
            page_num = page_info['page_index']
            start_date = page_info['start_date_obj']
            end_date = page_info['end_date_obj']
            
            if page_order not in pages_data:
                print(f"⚠️ Página {page_num + 1} sem dados da IA")
                continue
            
            entities = pages_data[page_order]['entities']
            
            if not entities:
                print(f"⚠️ Página {page_num + 1} sem entidades extraídas")
                continue
            
            # Extrai linhas da página
            page_rows = extractor.format_ai_data_to_rows(entities, start_date, end_date)
            
            if not page_rows:
                print(f"⚠️ Página {page_num + 1} sem linhas válidas")
                continue
            
            # Cria DataFrame da página
            page_df = pd.DataFrame(page_rows)
            
            # Cria calendário completo do período
            all_dates = pd.date_range(start=start_date, end=end_date, freq='D')
            calendar_df = pd.DataFrame(all_dates, columns=['Dia_dt'])
            
            # Merge com dados extraídos
            period_df = pd.merge(calendar_df, page_df, on='Dia_dt', how='left')
            period_df['page_order'] = page_order
            period_df['original_page'] = page_num + 1
            
            all_page_dataframes.append(period_df)

        if not all_page_dataframes:
            extractor.update_progress(3, 3, "Nenhuma linha de dados válida foi extraída.", status='completed')
            extractor.cleanup_gcs_files()
            return None

        # Concatena todos os DataFrames
        final_df = pd.concat(all_page_dataframes, ignore_index=True)
        
        # Ordena por data (ordem cronológica)
        final_df = final_df.sort_values('Dia_dt').reset_index(drop=True)

        # Formata colunas finais
        final_df['Dia'] = final_df['Dia_dt'].dt.strftime('%d/%m/%Y')
        day_map_pt = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
        final_df['Dia_Sema'] = final_df['Dia_dt'].dt.dayofweek.map(lambda x: day_map_pt[x])

        final_df.rename(columns={
            'entrada1': 'Entrada1',
            'saida1': 'Saida1',
            'entrada2': 'Entrada2',
            'saida2': 'Saida2',
            'entrada3': 'Entrada3',
            'saida3': 'Saida3'
        }, inplace=True)

        colunas_finais = ['Dia', 'Dia_Sema', 'Entrada1', 'Saida1', 'Entrada2', 'Saida2', 'Entrada3', 'Saida3']
        
        for col in colunas_finais:
            if col not in final_df.columns:
                final_df[col] = "0"

        final_df = final_df[colunas_finais].fillna("0")

        # Gera CSV
        output = BytesIO()
        final_df.to_csv(output, index=False, sep=';', encoding='utf-8-sig')
        output.seek(0)

        filename = f'Planalto_ponto_extraido_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        temp_file_path = os.path.join(tempfile.gettempdir(), f"{job.id}.csv")
        
        with open(temp_file_path, 'wb') as f:
            f.write(output.getvalue())

        extractor.cleanup_gcs_files()

        extractor.update_progress(3, 3, "Processamento concluído!", status='completed')

        job.meta.update({
            'status': 'completed',
            'file_path': temp_file_path,
            'filename': filename
        })
        job.save()

        return temp_file_path

    except Exception as e:
        error_message = f'Erro durante o processamento: {str(e)}'
        print(error_message)

        try:
            extractor.cleanup_gcs_files()
        except:
            pass

        job.meta.update({
            'status': 'error',
            'error': str(e)
        })
        job.save()
        return None

    finally:
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)

