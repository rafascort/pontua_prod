# /opt/pontua/AutoPonto/backend_api/queue_manager.py
import os
import tempfile
from datetime import datetime
import redis
from rq import Queue
import threading
import time
import traceback # Importar traceback para logs de erro detalhados

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from dotenv import load_dotenv

from auth_service import app as auth_app, db, User, jwt as auth_jwt, admin_required

load_dotenv()

app = auth_app
CORS(app, resources={r"/api/*": {"origins": ["http://localhost:3000", "https://sistemaponto.com", "https://sistemaponto.com.br"]}}, supports_credentials=True)

app.secret_key = os.getenv('FLASK_SECRET_KEY')

redis_conn = redis.Redis(host='localhost', port=6379, db=0)

# --- Filas Corrigidas (Apenas modelos 1, 6, 7) ---
QUEUES = {
    '1': Queue('jbs_queue', connection=redis_conn),
    '6': Queue('geral_ai_queue', connection=redis_conn),
    '7': Queue('geral_queue', connection=redis_conn),
    'period_extraction': Queue('period_extraction_queue', connection=redis_conn),
}

# --- Módulos Corrigidos ---
EXTRACTOR_MODULES = {
    '1': 'extractor_jbs',
    '6': 'extractor_geral_ai',
    '7': 'extractor_geral',
    'period_extraction': 'extractor_geral_ai',
}
# --- Fim das Correções ---


@app.route('/api/extract-periods', methods=['POST'])
@jwt_required()
def extract_periods():
    current_user_email = get_jwt_identity() # É o e-mail
    claims = get_jwt()
    if not claims.get('is_active'):
        return jsonify({"error": "A sua conta está inativa."}), 403
    try:
        if 'pdf_file' not in request.files:
            return jsonify({'error': 'Nenhum ficheiro PDF enviado.'}), 400

        file = request.files['pdf_file']
        pages = request.form.get('pages', '')

        if file.filename == '':
            return jsonify({'error': 'Nenhum ficheiro selecionado.'}), 400

        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            file.save(tmp_file.name)
            pdf_path = tmp_file.name

        q = QUEUES['period_extraction']
        
        job = q.enqueue(
            'extractor_geral_ai.extract_periods_task',
            pdf_path, pages, user_id=current_user_email, # Passa o e-mail
            job_timeout='2m',
            meta={'user_id': current_user_email, 'pdf_path': pdf_path, 'step': 'period_extraction'}
        )

        return jsonify({'task_id': job.id, 'status': 'queued', 'step': 'period_extraction'})
    except Exception as e:
        print(f"Erro ao colocar tarefa de extração de período na fila: {e}")
        traceback.print_exc()
        if 'pdf_path' in locals() and os.path.exists(pdf_path):
            try:
                os.unlink(pdf_path)
            except Exception as unlink_e:
                 print(f"Erro adicional ao tentar remover ficheiro temporário {pdf_path}: {unlink_e}")
        return jsonify({'error': 'Ocorreu um erro interno ao iniciar a análise do período.'}), 500


@app.route('/api/process', methods=['POST'])
@jwt_required()
def process_pdf():
    current_user_email = get_jwt_identity() # É o e-mail
    claims = get_jwt()
    if not claims.get('is_active'):
        return jsonify({"error": "A sua conta está inativa."}), 403

    try:
        data = request.get_json()
        pages_with_periods = data.get('pages_with_periods')
        pdf_path = data.get('pdf_path')
        model_type = data.get('model_type', '6') 

        if not pages_with_periods or not pdf_path:
            return jsonify({'error': 'Informações de período e caminho do PDF são necessárias.'}), 400

        if not os.path.exists(pdf_path):
             return jsonify({'error': f'Arquivo PDF não encontrado no servidor: {pdf_path}. Por favor, inicie o processo novamente.'}), 404

        if model_type not in ['1', '6']:
             return jsonify({'error': f'Tipo de modelo inválido ({model_type}). Modelos permitidos para esta rota: 1, 6.'}), 400
        
        if model_type not in QUEUES or model_type not in EXTRACTOR_MODULES:
            return jsonify({'error': 'Tipo de modelo inválido ou não configurado.'}), 400

        num_pages_to_process = len(pages_with_periods)
        if num_pages_to_process > 0:
            try:
                # --- CORREÇÃO APLICADA AQUI ---
                user = User.query.filter_by(email=current_user_email).first()
                if user and user.role != 'admin':
                    user.page_count += num_pages_to_process
                    db.session.commit()
                    print(f"Páginas atualizadas para {current_user_email}: +{num_pages_to_process} (Total: {user.page_count})")
                elif user:
                    print(f"Usuário {current_user_email} é admin, contagem não alterada.")
                else:
                    print(f"ERRO: Usuário {current_user_email} não encontrado para atualizar contagem.")
            except Exception as e:
                db.session.rollback()
                print(f"[ERROR] Falha ao atualizar contagem de páginas para o usuário {current_user_email}: {e}")
                traceback.print_exc()

        q = QUEUES[model_type]
        extractor_module_name = EXTRACTOR_MODULES[model_type]

        job = q.enqueue(f'{extractor_module_name}.process_pdf_task',
                        pdf_path, pages_with_periods, model_type, user_id=current_user_email,
                        job_timeout='1h',
                        meta={
                            'progress': 0, 'message': 'Tarefa na fila...',
                            'status': 'queued', 'current_step': 0, 'total_steps': 1,
                            'timestamp': datetime.now().isoformat(), 'user_id': current_user_email,
                            'step': 'full_processing'
                        })

        return jsonify({'task_id': job.id, 'message': 'Processamento completo na fila', 'status': 'queued', 'step': 'full_processing'})
    except Exception as e:
        print(f"Erro ao colocar tarefa na fila (/process): {e}")
        traceback.print_exc()
        return jsonify({'error': 'Ocorreu um erro interno ao iniciar o processamento.'}), 500

@app.route('/api/process-direct', methods=['POST'])
@jwt_required()
def process_pdf_direct():
    current_user_email = get_jwt_identity() # É o e-mail
    claims = get_jwt()
    if not claims.get('is_active'):
        return jsonify({"error": "A sua conta está inativa."}), 403

    try:
        if 'pdf_file' not in request.files:
            return jsonify({'error': 'Nenhum ficheiro PDF enviado.'}), 400

        file = request.files['pdf_file']
        pages = request.form.get('pages', '')
        model_type = '7'

        if file.filename == '':
            return jsonify({'error': 'Nenhum ficheiro selecionado.'}), 400

        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            file.save(tmp_file.name)
            pdf_path = tmp_file.name

        if model_type not in QUEUES or model_type not in EXTRACTOR_MODULES:
             if os.path.exists(pdf_path):
                 try: os.unlink(pdf_path)
                 except Exception as unlink_e: print(f"Erro ao remover ficheiro {pdf_path}: {unlink_e}")
             return jsonify({'error': f'Modelo {model_type} não está configurado no backend.'}), 400

        num_pages_to_process = 0
        if pages:
            page_list = []
            parts = pages.split(',')
            for part in parts:
                part = part.strip()
                if '-' in part:
                    try:
                        start, end = map(int, part.split('-'))
                        if start <= end:
                            page_list.extend(range(start, end + 1))
                    except ValueError: pass
                elif part.isdigit():
                    page_list.append(int(part))
            num_pages_to_process = len(set(page_list))

        if num_pages_to_process > 0:
            try:
                # --- CORREÇÃO APLICADA AQUI ---
                user = User.query.filter_by(email=current_user_email).first()
                if user and user.role != 'admin':
                    user.page_count += num_pages_to_process
                    db.session.commit()
                    print(f"Páginas atualizadas para {current_user_email}: +{num_pages_to_process} (Total: {user.page_count})")
                elif user:
                    print(f"Usuário {current_user_email} é admin, contagem não alterada.")
                else:
                    print(f"ERRO: Usuário {current_user_email} não encontrado para atualizar contagem.")
            except Exception as e:
                db.session.rollback()
                print(f"[ERROR] Falha ao atualizar contagem de páginas para o usuário {current_user_email}: {e}")
                traceback.print_exc()

        q = QUEUES[model_type]
        extractor_module_name = EXTRACTOR_MODULES[model_type]

        job = q.enqueue(f'{extractor_module_name}.process_pdf_task',
                        pdf_path, pages, model_type, user_id=current_user_email,
                        job_timeout='1h',
                        meta={
                            'progress': 0, 'message': 'Tarefa na fila...',
                            'status': 'queued', 'current_step': 0, 'total_steps': 1,
                            'timestamp': datetime.now().isoformat(), 'user_id': current_user_email,
                            'step': 'full_processing'
                        })

        return jsonify({'task_id': job.id, 'message': 'Processamento na fila', 'status': 'queued'})

    except Exception as e:
        print(f"Erro ao colocar tarefa na fila (/process-direct): {e}")
        traceback.print_exc()
        if 'pdf_path' in locals() and os.path.exists(pdf_path):
            try: os.unlink(pdf_path)
            except Exception as unlink_e: print(f"Erro ao remover ficheiro {pdf_path}: {unlink_e}")
        return jsonify({'error': 'Ocorreu um erro interno ao iniciar o processamento.'}), 500


@app.route('/api/progress/<task_id>', methods=['GET'])
@jwt_required()
def get_progress(task_id):
    current_user_email = get_jwt_identity()
    job = None
    for q in QUEUES.values():
        job = q.fetch_job(task_id)
        if job: break
    if not job:
        return jsonify({'error': 'Tarefa não encontrada'}), 404

    claims = get_jwt()
    if str(job.meta.get('user_id')) != str(current_user_email) and claims.get('role') != 'admin':
        return jsonify({"error": "Não tem permissão para ver o progresso desta tarefa."}), 403

    status_rq = job.get_status()
    progress_data = job.meta.copy()

    if status_rq == 'finished':
        internal_status = progress_data.get('status', 'completed')
        progress_data['status'] = internal_status
        if internal_status == 'completed':
            progress_data['result'] = job.result
            if progress_data.get('step') == 'period_extraction':
                progress_data['pdf_path'] = job.meta.get('pdf_path')
        elif internal_status == 'error':
             progress_data['error'] = job.meta.get('error', 'Erro desconhecido na tarefa.')
    elif status_rq == 'queued':
        progress_data['status'] = 'queued'
    elif status_rq == 'started':
        progress_data['status'] = 'processing'
    elif status_rq == 'failed':
        progress_data['status'] = 'error'
        progress_data['error'] = job.exc_info or job.meta.get('error', 'Tarefa falhou.')

    if progress_data.get('total_steps', 0) == 0:
        progress_data['total_steps'] = 1
    progress_data.pop('user_id', None)

    return jsonify(progress_data)

@app.route('/api/download/<task_id>', methods=['GET'])
@jwt_required()
def download_result(task_id):
    current_user_email = get_jwt_identity()
    job = None
    for q in QUEUES.values():
        job = q.fetch_job(task_id)
        if job: break
    if not job:
        return jsonify({'error': 'Tarefa não encontrada'}), 404

    claims = get_jwt()
    if str(job.meta.get('user_id')) != str(current_user_email) and claims.get('role') != 'admin':
        return jsonify({"error": "Não tem permissão para descarregar o resultado desta tarefa."}), 403

    if job.get_status() != 'finished' or job.meta.get('status') != 'completed':
        return jsonify({'error': 'A tarefa ainda não foi concluída ou falhou'}), 400

    file_path = job.meta.get('file_path')
    filename = job.meta.get('filename')

    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'Ficheiro de resultado não encontrado ou já removido'}), 404

    mimetype = 'text/csv'

    def remove_file_after_download(path_to_remove):
        time.sleep(5)
        try:
            os.unlink(path_to_remove)
            print(f"Ficheiro temporário {path_to_remove} removido após download.")
        except Exception as e:
            print(f"Erro ao remover ficheiro {path_to_remove}: {e}")

    cleanup_thread = threading.Thread(target=remove_file_after_download, args=(file_path,))
    cleanup_thread.daemon = True
    cleanup_thread.start()

    return send_file(file_path, mimetype=mimetype, as_attachment=True, download_name=filename)


@app.route('/api/health', methods=['GET'])
def health_check():
    try:
        redis_conn.ping()
        redis_status = "OK"
    except Exception as e:
        redis_status = f"ERROR: {str(e)}"
    return jsonify({ 'status': 'OK', 'redis_status': redis_status })
