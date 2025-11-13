# /opt/pontua/AutoPonto/backend_api/extractor_geral_ai.py
import os
import tempfile
import pandas as pd
from io import BytesIO
from datetime import datetime
from rq import get_current_job
from google.cloud import documentai_v1 as documentai
from google.cloud import storage # Import mantido por segurança
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
import re
import concurrent.futures
import threading
import traceback

from pdf2image import convert_from_path
import pytesseract
import platform

# Importa a biblioteca de Imagem (Pillow)
from PIL import Image

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
        
        # O GCS não é usado neste fluxo, mas mantemos os atributos
        # para consistência caso sejam usados em outro lugar.
        self.gcs_bucket_name = os.getenv('GCS_BUCKET_NAME')
        self.storage_client = storage.Client()
        self.upload_counter = 0
        self.upload_lock = threading.Lock()
        
        # Inicializa o cliente Document AI
        self.client = documentai.DocumentProcessorServiceClient(
            client_options={"api_endpoint": f"{self.location}-documentai.googleapis.com"}
        )
        self.processor_name = self.client.processor_path(self.project_id, self.location, self.processor_id)

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

    # Esta função não é mais chamada no fluxo do Modelo 6, mas mantida 
    # para não quebrar a importação do `extractor_geral`
    def cleanup_gcs_files(self):
        try:
            if not self.gcs_bucket_name:
                print("[LOG] Limpeza GCS pulada: Bucket não configurado.")
                return

            bucket = self.storage_client.bucket(self.gcs_bucket_name)
            prefix = f"{self.job.id}/"
            blobs = list(bucket.list_blobs(prefix=prefix))
            if blobs:
                self.update_progress(3, 3, f"Limpando {len(blobs)} arquivos temporários...", extra_info={'cleanup': True})
                for blob in blobs:
                    blob.delete()
        except Exception as e:
            print(f"⚠️ Erro ao limpar bucket: {e}")

    # Processa uma PÁGINA ÚNICA (como IMAGEM) de forma síncrona
    def process_document_page_sync(self, pdf_path, page_idx):
        """
        Converte uma única página de PDF em imagem e a envia 
        diretamente para o Document AI (processamento síncrono).
        Isso evita o bug do PdfWriter que corrompe o layout.
        """
        try:
            # 1. Converter a página específica do PDF para imagem
            images = convert_from_path(pdf_path, dpi=300, first_page=page_idx + 1, last_page=page_idx + 1)
            if not images:
                print(f"⚠️ Erro ao converter página {page_idx + 1} para imagem.")
                return []
            
            image = images[0]
            
            # 2. Converter a imagem (Pillow) para bytes
            image_bytes_io = BytesIO()
            # Usar JPEG é geralmente mais rápido e menor que PNG
            image.save(image_bytes_io, format='JPEG', quality=95)
            image_bytes = image_bytes_io.getvalue()
            
            # 3. Criar o request síncrono
            raw_document = documentai.RawDocument(
                content=image_bytes,
                mime_type='image/jpeg' # Envia como imagem
            )
            
            request = documentai.ProcessRequest(
                name=self.processor_name,
                raw_document=raw_document,
                skip_human_review=True
            )

            # 4. Chamar a API
            result = self.client.process_document(request=request)
            document = result.document
            
            # Retorna as entidades encontradas
            return document.entities

        except Exception as e:
            print(f"⚠️ Erro ao processar página {page_idx + 1} via bytes de imagem: {e}")
            traceback.print_exc()
            return []

    # Função adaptada para usar o processamento síncrono de imagem
    def process_pages_sync(self, pdf_path, pages_with_periods):
        
        pages_data = {}
        total_ai_pages = len(pages_with_periods)

        # Atualiza o progresso para a etapa 1 (Upload/Preparação)
        self.update_progress(1, 3, f"Iniciando processamento de {total_ai_pages} páginas...", extra_info={
            'ai_processing': True,
            'ai_total_pages': total_ai_pages,
            'ai_current_page': 0,
            'ai_message': "Iniciando IA..."
        })

        # Loop síncrono que chama a nova função
        for idx, page_info in enumerate(pages_with_periods):
            page_idx = page_info['page_index'] # O índice real da página no PDF
            
            # Atualiza a sub-etapa (progresso da IA)
            self.update_progress(1, 3, f"A processar página {idx + 1} de {total_ai_pages} pela IA...", extra_info={
                'ai_processing': True,
                'ai_total_pages': total_ai_pages,
                'ai_current_page': idx + 1,
                'ai_message': f"A processar {idx + 1}/{total_ai_pages} pela IA..."
            })
            
            # Chama a nova função que envia a IMAGEM
            entities = self.process_document_page_sync(pdf_path, page_idx)
            
            # 'idx' aqui é a 'page_order' (0, 1, 2...)
            pages_data[idx] = {'entities': entities} 

        self.update_progress(2, 3, "Recolhendo e consolidando resultados...", extra_info={'consolidating': True})
        return pages_data


    def format_ai_rows_by_order(self, entities):
        extracted_rows = []
        for entity in entities:
            if entity.type_.lower() == 'tabela_marcacoes' and entity.properties:
                row_data = {prop.type_.lower(): prop.mention_text.strip() for prop in entity.properties}
                
                # LOG REMOVIDO A PEDIDO
                # print(f"[LOG][Job {self.job.id if self.job else 'N/A'}] Entidade IA encontrada: {row_data}")

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

def normalize_time_format(value):
    """
    🔧 Normaliza horários para o formato HH:MM padrão.
    Corrige separadores incorretos, espaços e quebras de linha vindos do Document AI.
    """
    if pd.isna(value) or value == "0" or value == 0 or value == "":
        return "0"
    
    value_str = str(value).strip()
    
    if value_str == "0" or value_str == "":
        return "0"
    
    # 🔧 CRÍTICO: Remove TODOS os espaços em branco (espaços, tabs, quebras de linha)
    # Ex: "07 :48" → "07:48", "06:\n58" → "06:58", "18: 07" → "18:07"
    value_str = value_str.replace(' ', '').replace('\n', '').replace('\r', '').replace('\t', '')
    
    # Remove dois pontos finais duplicados ou isolados
    # Ex: "1817:" → "1817", "18::" → "18"
    value_str = re.sub(r':+$', '', value_str)
    
    # Procura padrão: HH:MM (agora sem espaços)
    # Exemplos: 12:00, 12-00, 12.00
    match = re.search(r'(\d{1,2})[^\d](\d{2})', value_str)
    if match:
        hour = match.group(1).zfill(2)  # Garante 2 dígitos
        minute = match.group(2)
        return f"{hour}:{minute}"
    
    # Tenta 4 dígitos sem separador: 1200 → 12:00, 1817 → 18:17
    if len(value_str) == 4 and value_str.isdigit():
        return f"{value_str[:2]}:{value_str[2:]}"
    
    # Tenta 3 dígitos: 600 → 06:00
    if len(value_str) == 3 and value_str.isdigit():
        return f"0{value_str[0]}:{value_str[1:]}"
    
    # Trata 2 dígitos como hora cheia: 18 → 18:00
    if len(value_str) == 2 and value_str.isdigit():
        return f"{value_str}:00"
    
    # Trata 1 dígito como hora cheia: 8 → 08:00
    if len(value_str) == 1 and value_str.isdigit():
        return f"0{value_str}:00"
    
    # ⚠️ Se nada funcionar, loga e retorna 0
    print(f"⚠️ [AVISO] Valor de horário não reconhecido: '{value}' → convertido para '0'")
    return "0"

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
        # Chama a função renomeada que agora usa o processamento síncrono por imagem
        pages_data = extractor.process_pages_sync(pdf_path, pages_with_periods)
        
        extractor.update_progress(2, 3, "A consolidar dados...", extra_info={'consolidating': True})
        
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
                print(f"[LOG][Job {job.id}] Aviso: Nenhum dado da IA para pág {page_num + 1}. Página ficará zerada.")
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
        
        # 🔧 VALIDAÇÃO E CORREÇÃO FINAL: Normaliza todos os horários antes de salvar
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

        print(f"[LOG][Job {job.id}] CSV gerado.")
        
        extractor.update_progress(3, 3, "Processamento concluído!", status='completed')
        job.meta.update({'status': 'completed', 'file_path': temp_file_path, 'filename': filename})
        job.save()

        print(f"[LOG][Job {job.id}] SUCESSO: Tarefa process_pdf_task concluída.")
        return temp_file_path
        
    except Exception as e:
        error_message = f'Erro no processamento principal: {str(e)}'
        print(f"[LOG][ERRO][Job {job.id}] {error_message}\n{traceback.format_exc()}")
        job.meta.update({'status': 'error', 'error': error_message})
        job.save()
        return None
    finally:
        # O pdf_path original (o arquivo completo) ainda precisa ser removido
        if os.path.exists(pdf_path):
            try:
                os.unlink(pdf_path)
            except Exception as e:
                print(f"[LOG][ERRO][Job {job.id}] Falha ao remover PDF temporário {pdf_path}: {e}")
