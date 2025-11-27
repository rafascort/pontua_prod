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

    def cleanup_gcs_files(self):
        try:
            bucket = self.storage_client.bucket(self.gcs_bucket_name)
            prefix = f"{self.job.id}/"
            blobs = list(bucket.list_blobs(prefix=prefix))
            if blobs:
                for blob in blobs:
                    blob.delete()
        except Exception as e:
            print(f"⚠️ Erro ao limpar bucket GCS para o job {self.job.id if self.job else 'N/A'}: {e}")


    def process_document_batch_async(self, pdf_path, page_range):
        """
        Processa um range de páginas de um PDF de forma assíncrona (em lote),
        removendo o limite de 15 páginas.
        """
        if not self.gcs_bucket_name:
            raise ValueError("Bucket do GCS não configurado.")

        try:
            reader = PdfReader(pdf_path, strict=False)
            total_pdf_pages = len(reader.pages)
        except PdfReadError as e:
            raise ValueError(f"PDF corrompido ou ilegível: {e}")

        page_indices_set = set()
        if page_range:
            range_parts = page_range.split(',')
            for part in range_parts:
                part = part.strip()
                if '-' in part:
                    sub_parts = part.split('-')
                    if len(sub_parts) == 2 and sub_parts[0].isdigit() and sub_parts[1].isdigit():
                        start_page = int(sub_parts[0]) - 1
                        end_page = int(sub_parts[1])
                        for i in range(start_page, min(end_page, total_pdf_pages)):
                            page_indices_set.add(i)
                elif part.isdigit():
                    page_num = int(part) - 1
                    if 0 <= page_num < total_pdf_pages:
                        page_indices_set.add(page_num)
        else:
            page_indices_set = set(range(total_pdf_pages))

        if not page_indices_set:
            raise ValueError("Nenhuma página válida para processar.")

        page_indices = sorted(list(page_indices_set))

        # --- NOVA LÓGICA DE ATUALIZAÇÃO DO META ---
        # Se a API não sabia o N de páginas (pages_to_process=0), atualizamos o meta agora.
        # Isso garante que a contagem no /download seja correta.
        if self.job and self.job.meta.get('pages_to_process', 0) == 0 and page_indices:
            try:
                num_pages_to_process = len(page_indices)
                self.job.meta['pages_to_process'] = num_pages_to_process
                self.job.save_meta()
                print(f"[LOG][Job {self.job.id}] Meta atualizado com 'pages_to_process': {num_pages_to_process}")
            except Exception as meta_e:
                print(f"[AVISO][Job {self.job.id}] Falha ao salvar meta 'pages_to_process': {meta_e}")
        # --- FIM DA NOVA LÓGICA ---

        self.update_progress(0, 3, "Preparando o ficheiro para análise...", status='processing')
        writer = PdfWriter()
        for page_idx in page_indices:
            if 0 <= page_idx < total_pdf_pages:
                writer.add_page(reader.pages[page_idx])

        if not writer.pages:
            raise ValueError("Nenhuma página foi adicionada ao novo PDF. Verifique os intervalos de páginas.")

        single_pdf_bytes = BytesIO()
        writer.write(single_pdf_bytes)
        single_pdf_bytes.seek(0)

        self.update_progress(1, 3, "A enviar o ficheiro para o servidor seguro...", status='processing')
        bucket = self.storage_client.bucket(self.gcs_bucket_name)
        blob_name = f"{self.job.id}/documento_completo.pdf"
        gcs_input_uri = f"gs://{self.gcs_bucket_name}/{blob_name}"
        bucket.blob(blob_name).upload_from_file(single_pdf_bytes, content_type="application/pdf")

        self.update_progress(2, 3, f"A processar {len(page_indices)} páginas pela IA (modo assíncrono)...", extra_info={'ai_processing': True})
        
        client = documentai.DocumentProcessorServiceClient(
            client_options={"api_endpoint": f"{self.location}-documentai.googleapis.com"}
        )

        gcs_document = documentai.GcsDocument(gcs_uri=gcs_input_uri, mime_type="application/pdf")
        
        output_config = documentai.DocumentOutputConfig(
            gcs_output_config={"gcs_uri": f"gs://{self.gcs_bucket_name}/{self.job.id}/output/"}
        )
        input_config = documentai.BatchDocumentsInputConfig(
            gcs_documents=documentai.GcsDocuments(documents=[gcs_document])
        )
        request = documentai.BatchProcessRequest(
            name=client.processor_path(self.project_id, self.location, self.processor_id),
            input_documents=input_config,
            document_output_config=output_config
        )

        operation = client.batch_process_documents(request)
        operation.result(timeout=3600)

        self.update_progress(3, 3, "A recolher e consolidar resultados...", extra_info={'consolidating': True})
        
        output_blobs = list(bucket.list_blobs(prefix=f"{self.job.id}/output/"))
        if not output_blobs:
            raise Exception("O processamento da IA não gerou arquivos de saída.")

        first_blob = output_blobs[0]
        doc_proto = documentai.Document.from_json(first_blob.download_as_bytes())
        
        return doc_proto.entities

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
                    'Entrada5': clean_time(row_data.get('entrada5', '0')),
                    'Saida5': clean_time(row_data.get('saida5', '0')),
                    'Entrada6': clean_time(row_data.get('entrada6', '0')),
                    'Saida6': clean_time(row_data.get('saida6', '0')),
                    'Entrada7': clean_time(row_data.get('entrada7', '0')),
                    'Saida7': clean_time(row_data.get('saida7', '0')),
                    'Entrada8': clean_time(row_data.get('entrada8', '0')),
                    'Saida8': clean_time(row_data.get('saida8', '0')),
                    'Entrada9': clean_time(row_data.get('entrada9', '0')),
                    'Saida9': clean_time(row_data.get('saida9', '0')),
                    'Entrada10': clean_time(row_data.get('entrada10', '0')),
                    'Saida10': clean_time(row_data.get('saida10', '0')),
                    'Entrada11': clean_time(row_data.get('entrada11', '0')),
                    'Saida11': clean_time(row_data.get('saida11', '0')),
                })
        
        return extracted_rows

def parse_flexible_date(date_str):
    if not date_str or date_str == '0':
        return pd.NaT
    
    # Remove espaços e caracteres estranhos
    date_str = str(date_str).strip()
    
    # Tenta formatos completos primeiro
    for fmt in ('%d/%m/%Y', '%d/%m/%y'):
        try:
            return pd.to_datetime(date_str, format=fmt)
        except (ValueError, TypeError):
            pass
    
    # Se a data veio sem ano (formato dd/mm), adiciona o ano atual
    if re.match(r'^\d{1,2}/\d{1,2}$', date_str):
        current_year = datetime.now().year
        date_str_with_year = f"{date_str}/{current_year}"
        try:
            return pd.to_datetime(date_str_with_year, format='%d/%m/%Y')
        except (ValueError, TypeError):
            pass
    
    return pd.NaT

def consolidate_duplicate_days(df):
    """
    EXCEÇÃO: Consolida dias duplicados coletando todos os horários e redistribuindo.
    Aplica apenas quando detecta fragmentação (múltiplas linhas com poucos horários).
    """
    # Identifica dias duplicados
    duplicate_dates = df[df.duplicated(subset=['Dia_dt'], keep=False)]['Dia_dt'].unique()
    
    if len(duplicate_dates) == 0:
        # Nenhum dia duplicado, retorna DataFrame original
        return df
    
    print(f"[LOG] Detectados {len(duplicate_dates)} dias com múltiplas entradas. Verificando fragmentação...")
    
    time_columns = [
        'Entrada1', 'Saida1', 'Entrada2', 'Saida2', 'Entrada3', 'Saida3', 'Entrada4', 'Saida4',
        'Entrada5', 'Saida5', 'Entrada6', 'Saida6', 'Entrada7', 'Saida7', 'Entrada8', 'Saida8',
        'Entrada9', 'Saida9', 'Entrada10', 'Saida10', 'Entrada11', 'Saida11'
    ]
    
    consolidated_rows = []
    processed_dates = set()
    
    for _, row in df.iterrows():
        date_val = row['Dia_dt']
        
        # Se não é duplicado ou já processamos, adiciona normalmente
        if date_val not in duplicate_dates or date_val in processed_dates:
            if date_val not in processed_dates:
                consolidated_rows.append(row)
                processed_dates.add(date_val)
            continue
        
        # Pega todas as linhas desta data
        date_rows = df[df['Dia_dt'] == date_val]
        
        # Verifica se é fragmentação (maioria das linhas com ≤2 horários)
        lines_with_few_times = 0
        for _, date_row in date_rows.iterrows():
            valid_times = sum(1 for col in time_columns 
                            if str(date_row[col]) not in ['0', '', 'nan', 'None'])
            if valid_times <= 2:
                lines_with_few_times += 1
        
        # Se maioria é fragmentada, consolida
        if lines_with_few_times >= len(date_rows) * 0.5:
            print(f"[LOG] Consolidando fragmentação para {row['Dia']}: {len(date_rows)} linhas")
            
            # Coleta todos os horários
            all_times = []
            for _, date_row in date_rows.iterrows():
                for col in time_columns:
                    time_val = str(date_row[col])
                    if time_val and time_val not in ['0', '', 'nan', 'None']:
                        all_times.append(time_val)
            
            # Remove duplicatas e ordena
            all_times = list(set(all_times))
            
            def time_to_minutes(t):
                try:
                    h, m = map(int, t.split(':'))
                    return h * 60 + m
                except:
                    return 9999
            
            all_times.sort(key=time_to_minutes)
            
            # Cria linha consolidada
            consolidated_row = row.copy()
            for col in time_columns:
                consolidated_row[col] = '0'
            
            for idx, time_val in enumerate(all_times[:22]):  # Máximo 22 horários (11 pares)
                consolidated_row[time_columns[idx]] = time_val
            
            consolidated_rows.append(consolidated_row)
        else:
            # Não é fragmentação, mantém apenas a primeira linha
            consolidated_rows.append(date_rows.iloc[0])
        
        processed_dates.add(date_val)
    
    return pd.DataFrame(consolidated_rows)

def fill_missing_days(df):
    """
    Preenche os dias que estão faltando no calendário entre a primeira e última data.
    """
    if df.empty or 'Dia_dt' not in df.columns:
        return df
    
    # Pega a data mínima e máxima
    min_date = df['Dia_dt'].min()
    max_date = df['Dia_dt'].max()
    
    print(f"[LOG] Preenchendo dias faltantes entre {min_date.strftime('%d/%m/%Y')} e {max_date.strftime('%d/%m/%Y')}")
    
    # Cria um range completo de datas
    full_date_range = pd.date_range(start=min_date, end=max_date, freq='D')
    
    # Cria um DataFrame com todas as datas
    full_df = pd.DataFrame({'Dia_dt': full_date_range})
    
    # Faz merge com os dados existentes, mantendo todas as datas
    result_df = full_df.merge(df, on='Dia_dt', how='left')
    
    # Preenche os dias faltantes com valores padrão
    result_df['Dia'] = result_df['Dia_dt'].dt.strftime('%d/%m/%Y')
    
    dias_semana_map = {
        0: 'seg', 1: 'ter', 2: 'qua', 3: 'qui', 4: 'sex', 5: 'sab', 6: 'dom'
    }
    result_df['Dia_Sema'] = result_df['Dia_dt'].dt.dayofweek.map(dias_semana_map)
    
    # Preenche horários faltantes com '0'
    time_columns = [
        'Entrada1', 'Saida1', 'Entrada2', 'Saida2', 'Entrada3', 'Saida3', 'Entrada4', 'Saida4',
        'Entrada5', 'Saida5', 'Entrada6', 'Saida6', 'Entrada7', 'Saida7', 'Entrada8', 'Saida8',
        'Entrada9', 'Saida9', 'Entrada10', 'Saida10', 'Entrada11', 'Saida11'
    ]
    for col in time_columns:
        result_df[col] = result_df[col].fillna('0')
    
    print(f"[LOG] Total de dias após preencher lacunas: {len(result_df)}")
    
    return result_df

def process_pdf_task(pdf_path, pages, model_type, user_id):
    job = get_current_job()
    if not job: 
        return None

    job.meta['user_id'] = user_id
    job.save_meta()

    extractor = ExtractorGeral(model_type, job)
    try:
        all_entities = extractor.process_document_batch_async(pdf_path, pages)
        
        print(f"[LOG][Job {job.id}] Total de entidades recebidas: {len(all_entities)}")
        
        if not all_entities:
            raise Exception("A IA não retornou nenhuma entidade.")
            
        all_rows = extractor.format_ai_rows_by_order(all_entities)
        
        print(f"[LOG][Job {job.id}] Total de linhas extraídas: {len(all_rows)}")
        if all_rows:
            print(f"[LOG][Job {job.id}] Amostra da primeira linha: {all_rows[0]}")

        if not all_rows:
            raise Exception("Nenhuma linha de marcação foi extraída pela IA.")
        
        full_final_df = pd.DataFrame(all_rows)
        
        print(f"[LOG][Job {job.id}] DataFrame criado com {len(full_final_df)} linhas")
        print(f"[LOG][Job {job.id}] Colunas: {full_final_df.columns.tolist()}")
        
        full_final_df['Dia_dt'] = full_final_df['Dia'].apply(parse_flexible_date)
        
        print(f"[LOG][Job {job.id}] Após parse de datas, linhas válidas: {full_final_df['Dia_dt'].notna().sum()}")
        
        full_final_df = full_final_df.dropna(subset=['Dia_dt'])
        full_final_df = full_final_df.sort_values(by='Dia_dt', ascending=True)
        
        print(f"[LOG][Job {job.id}] Antes da consolidação: {len(full_final_df)} linhas")
        
        # --- EXCEÇÃO: Consolida dias fragmentados (se houver) ---
        full_final_df = consolidate_duplicate_days(full_final_df)
        full_final_df = full_final_df.reset_index(drop=True)
        # --- FIM DA EXCEÇÃO ---
        
        print(f"[LOG][Job {job.id}] Após consolidação: {len(full_final_df)} linhas")
        
        # --- PREENCHE DIAS FALTANTES ---
        full_final_df = fill_missing_days(full_final_df)
        # --- FIM DO PREENCHIMENTO ---
        
        print(f"[LOG][Job {job.id}] Amostra do resultado final:")
        print(full_final_df.head(10).to_string())
        
        colunas_finais = [
            'Dia', 'Dia_Sema', 
            'Entrada1', 'Saida1', 'Entrada2', 'Saida2', 'Entrada3', 'Saida3', 'Entrada4', 'Saida4',
            'Entrada5', 'Saida5', 'Entrada6', 'Saida6', 'Entrada7', 'Saida7', 'Entrada8', 'Saida8',
            'Entrada9', 'Saida9', 'Entrada10', 'Saida10', 'Entrada11', 'Saida11'
        ]
        
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
        
        extractor.update_progress(1, 1, "Processamento concluído!", status='completed')
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
