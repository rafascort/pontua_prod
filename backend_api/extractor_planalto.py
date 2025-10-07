import os
import tempfile
import re
from datetime import datetime
from io import BytesIO
from typing import List, Dict, Tuple, Optional

import pandas as pd
import fitz # PyMuPDF

# Google Cloud imports
from google.cloud import storage
from google.cloud import documentai_v1 as documentai
from google.api_core.client_options import ClientOptions

# RQ imports
from rq import get_current_job

# ============================================
# ExtractorPlanaltoAI Class
# ============================================

class ExtractorPlanaltoAI:
    """
    Classe responsável por orquestrar a extração de dados de PDFs
    usando Google Document AI e gerenciar o fluxo de trabalho.
    """
    def __init__(self, model_type: Optional[str] = None, job=None):
        self.model_type = model_type
        self.job = job
        
        # Configurações do Google Cloud Storage (GCS)
        self.gcs_bucket_name = os.getenv('GCS_BUCKET_NAME', 'your-gcs-bucket-name')
        self.storage_client = storage.Client()

        # Configurações do Google Document AI
        self.docai_project_id = os.getenv('DOCAI_PROJECT_ID', 'your-docai-project-id')
        self.docai_location = os.getenv('DOCAI_LOCATION', 'us') # Ex: 'us' ou 'eu'
        
        # Mapeamento de model_type para IDs de processador Document AI
        # Você precisará configurar estes IDs no seu ambiente
        self.docai_processor_ids = {
            '1': os.getenv('DOCAI_PROCESSOR_ID_MODEL1', 'processor-id-for-model-1'),
            '2': os.getenv('DOCAI_PROCESSOR_ID_MODEL2', 'processor-id-for-model-2'),
            '3': os.getenv('DOCAI_PROCESSOR_ID_MODEL3', 'processor-id-for-model-3'),
            '5': os.getenv('DOCAI_PROCESSOR_ID_MODEL5', 'processor-id-for-model-5'),
            'debug-docai': os.getenv('DOCAI_PROCESSOR_ID_DEBUG', 'processor-id-for-debug'),
        }
        
        # Inicializa o cliente Document AI
        self.docai_client = documentai.DocumentProcessorServiceClient(
            client_options=ClientOptions(api_endpoint=f"{self.docai_location}-documentai.googleapis.com")
        )

    def update_progress(self, current: int, total: int, message: str, status: str = 'processing', meta: Optional[Dict] = None):
        """
        Atualiza o progresso da tarefa no objeto RQ Job.
        A prop 'meta' é usada para passar detalhes adicionais para o frontend (ProgressModal).
        """
        if self.job:
            self.job.meta['current_step'] = current
            self.job.meta['total_steps'] = total
            self.job.meta['message'] = message
            self.job.meta['status'] = status
            if meta:
                self.job.meta['meta'] = meta
            self.job.save_meta()

    def upload_to_gcs(self, file_content: bytes, destination_blob_name: str) -> str:
        """Faz upload de um arquivo para o GCS e retorna a URI."""
        bucket = self.storage_client.bucket(self.gcs_bucket_name)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_string(file_content, content_type='application/pdf')
        return f"gs://{self.gcs_bucket_name}/{destination_blob_name}"

    def download_from_gcs(self, source_blob_name: str) -> bytes:
        """Faz download de um arquivo do GCS."""
        bucket = self.storage_client.bucket(self.gcs_bucket_name)
        blob = bucket.blob(source_blob_name)
        return blob.download_as_bytes()

    def cleanup_gcs_files(self):
        """Remove arquivos temporários do GCS criados durante o processamento."""
        try:
            bucket = self.storage_client.bucket(self.gcs_bucket_name)
            # Remove páginas temporárias
            blobs = list(bucket.list_blobs(prefix=f'temp_pages/{self.job.id}_'))
            for blob in blobs:
                blob.delete()
            # Remove outputs temporários (se houver)
            blobs = list(bucket.list_blobs(prefix=f'temp_output/{self.job.id}_'))
            for blob in blobs:
                blob.delete()
        except Exception as e:
            print(f"⚠️ Erro ao limpar arquivos GCS: {e}")

    def _parse_page_range(self, page_range_str: str) -> List[int]:
        """
        Analisa uma string de intervalo de páginas (ex: "1-3,5")
        e retorna uma lista de índices de página baseados em 0.
        """
        pages = set()
        for part in page_range_str.split(','):
            part = part.strip()
            if '-' in part:
                start, end = map(int, part.split('-'))
                pages.update(range(start - 1, end)) # Converte para 0-based
            else:
                pages.add(int(part) - 1) # Converte para 0-based
        return sorted(list(pages))

    def _extract_periods_from_page(self, page_text: str, page_index: int) -> List[Dict]:
        """
        Extrai potenciais períodos de data do texto de uma única página.
        Esta é uma implementação de exemplo e pode precisar de ajustes
        para os formatos de data específicos do seu documento.
        """
        found_dates = []
        
        # Padrões de regex para datas comuns em português
        date_patterns = [
            r'\b(\d{1,2}/\d{1,2}/\d{4})\b', # DD/MM/YYYY
            r'\b(\d{1,2}\s+de\s+(?:janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+\d{4})\b', # DD de Mês de YYYY
            r'\b(\d{4}-\d{2}-\d{2})\b' # YYYY-MM-DD
        ]
        
        month_map = {
            'janeiro': '01', 'fevereiro': '02', 'março': '03', 'abril': '04',
            'maio': '05', 'junho': '06', 'julho': '07', 'agosto': '08',
            'setembro': '09', 'outubro': '10', 'novembro': '11', 'dezembro': '12'
        }

        for pattern in date_patterns:
            for match in re.finditer(pattern, page_text, re.IGNORECASE):
                original_date_str = match.group(1)
                parsed_date = None
                try:
                    if '/' in original_date_str:
                        parsed_date = datetime.strptime(original_date_str, '%d/%m/%Y').strftime('%Y-%m-%d')
                    elif ' de ' in original_date_str.lower():
                        parts = original_date_str.lower().split(' de ')
                        day = parts[0]
                        month_name = parts[1]
                        year = parts[2]
                        month_num = month_map.get(month_name)
                        if month_num:
                            parsed_date = f"{year}-{month_num}-{day.zfill(2)}"
                    elif '-' in original_date_str: # Assume YYYY-MM-DD
                        parsed_date = original_date_str
                    
                    if parsed_date:
                        found_dates.append({
                            'page': page_index + 1, # Página 1-based para o frontend
                            'original': original_date_str,
                            'date': parsed_date # Formato padronizado YYYY-MM-DD
                        })
                except ValueError:
                    # Ignora datas que não puderam ser analisadas
                    pass
        
        # Remove duplicatas mantendo a ordem de descoberta
        unique_dates = []
        seen_keys = set()
        for d in found_dates:
            key = (d['page'], d['original'], d['date'])
            if key not in seen_keys:
                unique_dates.append(d)
                seen_keys.add(key)
        
        return unique_dates

    def split_and_extract_periods(self, pdf_path: str, pages_str: str) -> List[Dict]:
        """
        Divide o PDF em páginas e extrai potenciais períodos de data das páginas especificadas.
        Retorna uma lista de dicionários com número da página, string de data original e data analisada.
        """
        self.update_progress(0, 0, "Carregando PDF e extraindo texto para datas...", meta={'step_type': 'initial_date_extraction'})
        
        all_extracted_dates = []
        
        try:
            doc = fitz.open(pdf_path)
            selected_page_indices = self._parse_page_range(pages_str)
            
            total_pages_to_process = len(selected_page_indices)
            
            for i, page_index in enumerate(selected_page_indices):
                if page_index < 0 or page_index >= doc.page_count:
                    print(f"Página {page_index + 1} fora do intervalo do documento. Ignorando.")
                    continue
                
                page = doc.load_page(page_index)
                text = page.get_text("text")
                
                dates_on_page = self._extract_periods_from_page(text, page_index)
                all_extracted_dates.extend(dates_on_page)
                
                self.update_progress(i + 1, total_pages_to_process, f"Extraindo datas da página {page_index + 1}...", meta={'step_type': 'initial_date_extraction'})
                
            doc.close()
            
            # Ordena por página e depois por data para consistência
            all_extracted_dates.sort(key=lambda x: (x['page'], x['date']))
            
            self.update_progress(total_pages_to_process, total_pages_to_process, "Extração inicial de datas concluída.", status='completed', meta={'step_type': 'initial_date_extraction'})
            
            return all_extracted_dates
            
        except Exception as e:
            print(f"Erro em split_and_extract_periods: {e}")
            raise

    def _process_single_page_with_docai(self, gcs_input_uri: str, processor_id: str) -> Dict:
        """Processa uma única página usando o Google Document AI."""
        processor_name = self.docai_client.processor_path(self.docai_project_id, self.docai_location, processor_id)
        
        gcs_document = documentai.GcsDocument(gcs_uri=gcs_input_uri, mime_type='application/pdf')
        input_config = documentai.DocumentInputConfig(gcs_document=gcs_document)
        
        request = documentai.ProcessRequest(name=processor_name, input_config=input_config)
        
        response = self.docai_client.process_document(request)
        
        # --- Lógica de extração de dados do Document AI ---
        # Esta parte precisa ser adaptada à saída específica do seu processador Document AI.
        # O exemplo abaixo é genérico.
        
        extracted_data = {
            'page_number': response.document.pages[0].page_number if response.document.pages else None,
            'entities': []
        }
        
        for entity in response.document.entities:
            # Exemplo: extrair tipo, texto e valor normalizado
            entity_info = {
                'type': entity.type,
                'mention_text': entity.mention_text,
                'normalized_value': entity.normalized_value.text_value if entity.normalized_value else None
            }
            extracted_data['entities'].append(entity_info)
        
        return extracted_data

    def process_pages_parallel(self, pdf_path: str, pages_with_periods: List[Dict]) -> List[Dict]:
        """
        Processa as páginas selecionadas em "paralelo" usando Document AI.
        `pages_with_periods` contém as datas confirmadas e informações da página.
        """
        self.update_progress(0, len(pages_with_periods), "Preparando páginas para processamento de IA...", meta={'step_type': 'ai_processing'})
        
        processed_pages_data = []
        
        doc = fitz.open(pdf_path)
        
        processing_tasks = []
        
        for i, page_info in enumerate(pages_with_periods):
            page_index = page_info['page'] - 1 # Converte para 0-based
            if page_index < 0 or page_index >= doc.page_count:
                print(f"Página {page_info['page']} fora do intervalo do documento. Ignorando.")
                continue
            
            page = doc.load_page(page_index)
            page_pdf_bytes = BytesIO(page.get_pdf_bytes())
            
            # Upload do PDF de página única para o GCS
            gcs_blob_name = f"temp_pages/{self.job.id}_page_{page_index + 1}.pdf"
            gcs_uri = self.upload_to_gcs(page_pdf_bytes.getvalue(), gcs_blob_name)
            
            processing_tasks.append({
                'gcs_uri': gcs_uri,
                'page_info': page_info,
                'processor_id': self.docai_processor_ids.get(self.model_type)
            })
            
            self.update_progress(i + 1, len(pages_with_periods), f"Página {page_info['page']} preparada para IA...", meta={'step_type': 'ai_processing'})
            
        doc.close()
        
        # Para um ambiente de produção com processamento paralelo real,
        # você usaria um pool de threads/processos ou uma solução assíncrona aqui.
        # Por simplicidade, processamos sequencialmente neste exemplo.
        for i, task in enumerate(processing_tasks):
            self.update_progress(i, len(processing_tasks), f"Processando página {task['page_info']['page']} com Document AI...", meta={'step_type': 'ai_processing'})
            try:
                docai_output = self._process_single_page_with_docai(task['gcs_uri'], task['processor_id'])
                processed_pages_data.append({
                    'page_info': task['page_info'],
                    'docai_output': docai_output
                })
            except Exception as e:
                print(f"Erro ao processar página {task['page_info']['page']} com Document AI: {e}")
                # Decida como lidar com erros: pular, tentar novamente ou levantar exceção
                pass
        
        self.update_progress(len(pages_with_periods), len(pages_with_periods), "Processamento de IA concluído.", status='processing', meta={'step_type': 'ai_processing'})
        
        return processed_pages_data

    def organize_chronologically(self, pages_data: List[Dict], pages_with_periods: List[Dict]) -> pd.DataFrame:
        """
        Organiza os dados extraídos cronologicamente e os formata em um DataFrame.
        Esta é a etapa onde a saída do Document AI é analisada e estruturada.
        """
        self.update_progress(0, 1, "Organizando dados cronologicamente...", meta={'step_type': 'data_organization'})
        
        all_records = []
        
        # Garante que pages_with_periods estejam ordenadas por página e depois por data
        pages_with_periods.sort(key=lambda x: (x['page'], datetime.strptime(x['date'], '%Y-%m-%d')))
        
        for page_data in pages_data:
            page_info = page_data['page_info']
            docai_output = page_data['docai_output']
            
            # Usa a data confirmada do page_info
            confirmed_date_str = page_info['date'] # Formato YYYY-MM-DD
            confirmed_date_obj = datetime.strptime(confirmed_date_str, '%Y-%m-%d').date()
            
            # --- Lógica de parsing da saída do Document AI ---
            # Você precisará adaptar esta lógica para extrair os campos relevantes
            # com base nos tipos de entidade definidos no seu processador Document AI.
            
            record = {
                'Dia_dt': confirmed_date_obj,
                'Pagina': page_info['page'],
                'Original_Date_Str': page_info['original'],
                'Valor_Campo_A': None, # Exemplo de campo
                'Valor_Campo_B': None, # Exemplo de campo
                # Adicione mais campos conforme necessário
            }
            
            for entity in docai_output.get('entities', []):
                if entity['type'] == 'campo_a': # Substitua 'campo_a' pelo tipo de entidade real
                    record['Valor_Campo_A'] = entity['mention_text']
                elif entity['type'] == 'campo_b': # Substitua 'campo_b' pelo tipo de entidade real
                    record['Valor_Campo_B'] = entity['mention_text']
                # Adicione mais lógica de parsing de entidade aqui
            
            all_records.append(record)
            
        if not all_records:
            return pd.DataFrame()
            
        df = pd.DataFrame(all_records)
        
        # Ordena pelo campo de data
        df = df.sort_values(by='Dia_dt').reset_index(drop=True)
        
        # Define as colunas finais e preenche as ausentes com "0"
        # Ajuste esta lista para corresponder às colunas que você espera no CSV final
        colunas_finais = ['Dia_dt', 'Pagina', 'Original_Date_Str', 'Valor_Campo_A', 'Valor_Campo_B'] 
        for col in colunas_finais:
            if col not in df.columns:
                df[col] = "0"
        
        df = df[colunas_finais].fillna("0")
        
        self.update_progress(1, 1, "Dados organizados.", status='processing', meta={'step_type': 'data_organization'})
        
        return df

    def generate_final_csv(self, final_df: pd.DataFrame) -> Tuple[BytesIO, str]:
        """Gera o arquivo CSV final a partir do DataFrame."""
        self.update_progress(0, 1, "Gerando arquivo CSV...", meta={'step_type': 'csv_generation'})
        
        output = BytesIO()
        final_df.to_csv(output, index=False, sep=';', encoding='utf-8-sig')
        output.seek(0)
        
        filename = f'Planalto_ponto_extraido_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        self.update_progress(1, 1, "CSV gerado.", status='completed', meta={'step_type': 'csv_generation'})
        
        return output, filename

# ============================================
# TASKS RQ
# ============================================

def extract_periods_task(pdf_path: str, pages: str, user_id: str, **kwargs):
    """
    PASSO 2: Task para extrair períodos das páginas para revisão do usuário.
    Retorna uma lista de dicionários com informações das datas encontradas.
    """
    job = get_current_job()
    if not job:
        return None
    
    job.meta['user_id'] = user_id
    job.save_meta()
    
    # model_type não é necessário para a extração inicial de datas
    extractor = ExtractorPlanaltoAI(job=job) 
    
    try:
        # Extrai períodos
        pages_info = extractor.split_and_extract_periods(pdf_path, pages)
        
        # Salva informações no job para o próximo passo
        job.meta.update({
            'status': 'periods_extracted',
            'pages_info': pages_info, # Esta será a lista de datas extraídas
            'pdf_path': pdf_path,
            'message': 'Períodos extraídos com sucesso. Aguardando confirmação do usuário.'
        })
        job.save()
        
        return pages_info # Retorna as datas para o frontend
        
    except Exception as e:
        error_message = f'Erro ao extrair períodos: {str(e)}'
        print(error_message)
        job.meta.update({
            'status': 'error',
            'error': str(e),
            'message': error_message
        })
        job.save()
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)
        return None

def process_pdf_task(pdf_path: str, pages_with_periods: List[Dict], model_type: str, user_id: str, **kwargs):
    """
    PASSOS 5-8: Task para processar páginas confirmadas pelo usuário.
    Args:
        pdf_path: Caminho do PDF temporário no servidor.
        pages_with_periods: Lista de dicts com as datas confirmadas pelo usuário.
            Ex: [{'page': 1, 'original': '01/02/2025', 'date': '2025-02-01'}, ...]
        model_type: O tipo de modelo selecionado pelo usuário.
        user_id: ID do usuário que iniciou a tarefa.
    """
    job = get_current_job()
    if not job:
        return None
    
    job.meta['user_id'] = user_id
    job.save_meta()
    
    extractor = ExtractorPlanaltoAI(model_type, job)
    
    try:
        extractor.update_progress(0, 4, "Iniciando processamento...", meta={'step_type': 'overall'})
        
        # PASSO 5: Processa todas as páginas simultaneamente com Document AI
        extractor.update_progress(1, 4, "Processando páginas com IA...", meta={'step_type': 'ai_processing'})
        pages_data = extractor.process_pages_parallel(pdf_path, pages_with_periods)
        
        if not pages_data:
            raise ValueError("Nenhuma página foi processada com sucesso pelo Document AI.")
            
        # PASSO 7: Organiza em ordem cronológica
        extractor.update_progress(2, 4, "Organizando dados em ordem cronológica...", meta={'step_type': 'data_organization'})
        final_df = extractor.organize_chronologically(pages_data, pages_with_periods)
        
        if final_df is None or final_df.empty:
            extractor.update_progress(
                4, 4,
                "Nenhuma linha de dados válida foi extraída.",
                status='completed',
                meta={'step_type': 'overall'}
            )
            extractor.cleanup_gcs_files()
            return None
            
        # PASSO 8: Gera CSV final
        extractor.update_progress(3, 4, "Gerando arquivo CSV...", meta={'step_type': 'csv_generation'})
        output, filename = extractor.generate_final_csv(final_df)
        
        # Salva o arquivo CSV temporário no sistema de arquivos local do worker RQ
        temp_file_path = os.path.join(tempfile.gettempdir(), f"{job.id}.csv")
        with open(temp_file_path, 'wb') as f:
            f.write(output.getvalue())
            
        # Limpa arquivos temporários do GCS
        extractor.cleanup_gcs_files()
        
        # Atualiza o job com o status final e metadados
        extractor.update_progress(4, 4, "Processamento concluído!", status='completed', meta={'step_type': 'overall'})
        job.meta.update({
            'status': 'completed',
            'file_path': temp_file_path, # Caminho para o arquivo no worker RQ
            'filename': filename,
            'total_rows': len(final_df),
            'date_range': {
                'start': final_df['Dia_dt'].min().strftime('%d/%m/%Y') if not final_df.empty else 'N/A',
                'end': final_df['Dia_dt'].max().strftime('%d/%m/%Y') if not final_df.empty else 'N/A'
            }
        })
        job.save()
        
        return temp_file_path # Retorna o caminho do arquivo para o backend principal
        
    except Exception as e:
        error_message = f'Erro durante o processamento: {str(e)}'
        print(error_message)
        try:
            extractor.cleanup_gcs_files()
        except:
            pass # Ignora erros na limpeza se já houver um erro principal
        job.meta.update({
            'status': 'error',
            'error': str(e),
            'message': error_message
        })
        job.save()
        return None
        
    finally:
        # Garante que o PDF temporário original seja removido
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)


