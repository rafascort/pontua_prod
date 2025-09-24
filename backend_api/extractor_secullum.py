import os
import tempfile
import pandas as pd
from io import BytesIO
import cv2
import numpy as np
import logging
import re
from datetime import datetime
from rq import get_current_job
from pdf2image import convert_from_path
from PIL import Image

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

try:
    from paddleocr import PaddleOCR
    PADDLE_OK = True
except ImportError:
    PADDLE_OK = False
    logging.error("PaddleOCR não está instalado. Verifique o ambiente.")

class ExtractorPontoEletronico:
    def __init__(self, model_type='6', job=None):
        self.job = job
        if not PADDLE_OK:
            raise ImportError("PaddleOCR não disponível")
        
        log_id = self.job.id if self.job else 'N/A'
        logging.info(f"[Job {log_id}] Inicializando PaddleOCR...")
        # Corrigido para não usar argumentos incompatíveis
        self.ocr = PaddleOCR(lang='pt', use_angle_cls=True)
        logging.info(f"[Job {log_id}] PaddleOCR pronto!")

    def update_progress(self, current_step, total_steps, message, status='processing'):
        if self.job:
            progress = int((current_step / max(total_steps, 1)) * 100)
            self.job.meta.update({'progress': progress, 'message': message, 'status': status, 'current_step': current_step, 'total_steps': total_steps})
            self.job.save()

    def extrair_texto_paddle(self, imagem):
        img_array = np.array(imagem)
        logging.info(f"[Job {self.job.id}] Executando OCR...")
        resultado = self.ocr.ocr(img_array)

        # Verificação de segurança para o resultado do OCR
        if not resultado or not resultado[0]:
            logging.warning(f"[Job {self.job.id}] PaddleOCR não retornou resultados.")
            return []
            
        # Filtra os resultados com base na confiança
        textos_filtrados = [line[1][0] for line in resultado[0] if line and len(line) >= 2 and isinstance(line[1], (list, tuple)) and len(line[1]) >= 2 and line[1][1] > 0.7]
        return textos_filtrados

    def identificar_dados_exatos(self, textos: list):
        log_header = f"[Job {self.job.id}]"
        texto_completo_para_log = ' '.join(textos)
        logging.info(f"{log_header} --- TEXTO BRUTO OCR ---\n{texto_completo_para_log}\n{log_header} --- FIM TEXTO BRUTO ---")

        dados_extraidos = []
        # Padrão para encontrar uma linha de ponto que COMEÇA com uma data
        padrao_linha = re.compile(r'^(\d{2}/\d{2}/\d{2,4})\s*-\s*([a-zA-ZçÇãÃáÁéÉíÍóÓúÚ]+)\s*(.*)')

        # AJUSTE PRINCIPAL: Analisar cada texto detectado individualmente
        for linha in textos:
            match = padrao_linha.search(linha.strip())
            if not match:
                continue
            
            data_str, dia_semana, resto_linha = match.groups()

            try:
                data_obj = datetime.strptime(data_str, '%d/%m/%y') if len(data_str.split('/')[-1]) == 2 else datetime.strptime(data_str, '%d/%m/%Y')
                data_formatada = data_obj.strftime('%d/%m/%Y')
            except ValueError:
                continue

            horarios = re.findall(r'(\d{2}:\d{2})', resto_linha)
            horarios_finais = ["0", "0", "0", "0"]

            if "folga" in resto_linha.lower():
                pass
            elif len(horarios) >= 2:
                horarios_finais[0], horarios_finais[1] = horarios[0], horarios[1]
                if len(horarios) >= 4:
                    horarios_finais[2], horarios_finais[3] = horarios[2], horarios[3]

            dados_extraidos.append({
                'Dia': data_formatada, 'Dia_Semana': dia_semana[:3].capitalize(),
                'Entrada1': horarios_finais[0], 'Saida1': horarios_finais[1],
                'Entrada2': horarios_finais[2], 'Saida2': horarios_finais[3]
            })
            
        if dados_extraidos:
            dados_extraidos.sort(key=lambda x: datetime.strptime(x['Dia'], '%d/%m/%Y'))
        return dados_extraidos

    def processar_pdf(self, pdf_path, pages_range=None):
        pages_args = {}
        if pages_range and '-' in pages_range:
            start, end = map(int, pages_range.split('-'))
            pages_args['first_page'], pages_args['last_page'] = start, end
        elif pages_range:
            pages_args['first_page'] = pages_args['last_page'] = int(pages_range)
        
        imagens = convert_from_path(pdf_path, dpi=300, **pages_args)
        self.update_progress(0, len(imagens), f"PDF convertido: {len(imagens)} páginas.")

        todos_dados = []
        for i, imagem in enumerate(imagens):
            self.update_progress(i + 1, len(imagens), f"Processando página {i+1}...")
            textos = self.extrair_texto_paddle(imagem)
            if textos:
                dados_pagina = self.identificar_dados_exatos(textos)
                todos_dados.extend(dados_pagina)
        return todos_dados

def process_pdf_task(pdf_path, pages, model_type, user_id):
    job = get_current_job()
    if not job: logging.error("Não foi possível obter o objeto job do RQ."); return None
    job.meta['user_id'] = user_id; job.save_meta()
    
    try:
        extrator = ExtractorPontoEletronico(model_type, job)
        dados = extrator.processar_pdf(pdf_path, pages)
        
        logging.info(f"[Job {job.id}] DADOS FINAIS: {dados}")

        if not dados:
            extrator.update_progress(1, 1, "Nenhum dado válido foi encontrado.", status='completed')
            return None
            
        df = pd.DataFrame(dados)
        df = df.reindex(columns=['Dia', 'Dia_Semana', 'Entrada1', 'Saida1', 'Entrada2', 'Saida2'], fill_value="0")
        output = BytesIO()
        df.to_csv(output, index=False, encoding='utf-8', sep=';')
        output.seek(0)
        
        temp_path = os.path.join(tempfile.gettempdir(), f"{job.id}.csv")
        with open(temp_path, 'wb') as f: f.write(output.getvalue())
            
        filename = f'Secullum_Ponto_Extraido_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        job.meta.update({'status': 'completed', 'file_path': temp_path, 'filename': filename, 'message': f'{len(dados)} registros extraídos com sucesso!'})
        job.save()
        return temp_path
        
    except Exception as e:
        logging.error(f"Erro fatal na tarefa {job.id}: {e}", exc_info=True)
        job.meta.update({'status': 'error', 'error': str(e)}); job.save()
        return None
    finally:
        if os.path.exists(pdf_path): os.unlink(pdf_path)
