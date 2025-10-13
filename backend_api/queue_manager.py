# /opt/pontua/AutoPonto/backend_api/queue_manager.py
import os
import tempfile
from datetime import datetime
import redis
from rq import Queue
import threading
import time

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

QUEUES = {
    '1': Queue('jbs_queue', connection=redis_conn),
    '2': Queue('brf_queue', connection=redis_conn),
    '3': Queue('pontomais_queue', connection=redis_conn),
    '5': Queue('planalto_queue', connection=redis_conn),
    '6': Queue('geral_ai_queue', connection=redis_conn),
    '7': Queue('geral_queue', connection=redis_conn),
    'period_extraction': Queue('period_extraction_queue', connection=redis_conn),
}

EXTRACTOR_MODULES = {
    '1': 'extractor_jbs',
    '2': 'extractor_brf',
    '3': 'extractor_pontomais',
    '5': 'extractor_planalto',
    '6': 'extractor_geral_ai',
    '7': 'extractor_geral',
    'period_extraction': 'extractor_geral_ai',
}

@app.route('/api/extract-periods', methods=['POST'])
@jwt_required()
def extract_periods():
    current_user_id = get_jwt_identity()
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
            pdf_path, pages, user_id=current_user_id,
            job_timeout='2m',
            meta={'user_id': current_user_id, 'pdf_path': pdf_path}
        )
                        
        return jsonify({'task_id': job.id, 'status': 'queued', 'step': 'period_extraction'})
    except Exception as e:
        print(f"Erro ao colocar tarefa de extração de período na fila: {e}")
        return jsonify({'error': 'Ocorreu um erro interno ao iniciar a análise do período.'}), 500

@app.route('/api/process', methods=['POST'])
@jwt_required()
def process_pdf():
    current_user_id = get_jwt_identity()
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

        if model_type not in QUEUES or model_type not in EXTRACTOR_MODULES:
            return jsonify({'error': 'Tipo de modelo inválido.'}), 400
        
        num_pages_to_process = len(pages_with_periods)
        if num_pages_to_process > 0:
            try:
                user = User.query.get(current_user_id)
                if user and user.role != 'admin':
                    user.page_count += num_pages_to_process
                    db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"[ERROR] Falha ao atualizar contagem de páginas para o usuário {current_user_id}: {e}")
        
        q = QUEUES[model_type]
        extractor_module_name = EXTRACTOR_MODULES[model_type]
        
        job = q.enqueue(f'{extractor_module_name}.process_pdf_task',
                        pdf_path, pages_with_periods, model_type, user_id=current_user_id,
                        job_timeout='1h',
                        meta={
                            'progress': 0, 'message': 'Tarefa na fila...',
                            'status': 'queued', 'current_step': 0, 'total_steps': 1,
                            'timestamp': datetime.now().isoformat(), 'user_id': current_user_id
                        })
                        
        return jsonify({'task_id': job.id, 'message': 'Processamento completo na fila', 'status': 'queued', 'step': 'full_processing'})
    except Exception as e:
        print(f"Erro ao colocar tarefa na fila: {e}")
        return jsonify({'error': 'Ocorreu um erro interno ao iniciar o processamento.'}), 500

@app.route('/api/process-direct', methods=['POST'])
@jwt_required()
def process_pdf_direct():
    current_user_id = get_jwt_identity()
    claims = get_jwt()
    if not claims.get('is_active'):
        return jsonify({"error": "A sua conta está inativa."}), 403

    try:
        if 'pdf_file' not in request.files:
            return jsonify({'error': 'Nenhum ficheiro PDF enviado.'}), 400
        
        file = request.files['pdf_file']
        pages = request.form.get('pages', '')
        model_type = request.form.get('model_type', '7')

        if file.filename == '':
            return jsonify({'error': 'Nenhum ficheiro selecionado.'}), 400

        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            file.save(tmp_file.name)
            pdf_path = tmp_file.name

        if model_type not in QUEUES or model_type not in EXTRACTOR_MODULES:
            return jsonify({'error': 'Tipo de modelo inválido.'}), 400
        
        num_pages_to_process = 0
        if pages:
            if '-' in pages:
                try:
                    start, end = map(int, pages.split('-'))
                    num_pages_to_process = end - start + 1
                except ValueError:
                    num_pages_to_process = 1
            else:
                num_pages_to_process = len(pages.split(','))
        
        if num_pages_to_process > 0:
            try:
                user = User.query.get(current_user_id)
                if user and user.role != 'admin':
                    user.page_count += num_pages_to_process
                    db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"[ERROR] Falha ao atualizar contagem de páginas para o usuário {current_user_id}: {e}")

        q = QUEUES[model_type]
        extractor_module_name = EXTRACTOR_MODULES[model_type]
        
        job = q.enqueue(f'{extractor_module_name}.process_pdf_task',
                        pdf_path, pages, model_type, user_id=current_user_id,
                        job_timeout='1h',
                        meta={
                            'progress': 0, 'message': 'Tarefa na fila...',
                            'status': 'queued', 'current_step': 0, 'total_steps': 1,
                            'timestamp': datetime.now().isoformat(), 'user_id': current_user_id
                        })
                        
        return jsonify({'task_id': job.id, 'message': 'Processamento na fila', 'status': 'queued'})

    except Exception as e:
        print(f"Erro ao colocar tarefa na fila: {e}")
        return jsonify({'error': 'Ocorreu um erro interno ao iniciar o processamento.'}), 500

@app.route('/api/progress/<task_id>', methods=['GET'])
@jwt_required()
def get_progress(task_id):
    current_user_id = get_jwt_identity()
    job = None
    for q in QUEUES.values():
        job = q.fetch_job(task_id)
        if job: break
    if not job:
        return jsonify({'error': 'Tarefa não encontrada'}), 404
    claims = get_jwt()
    if job.meta.get('user_id') != current_user_id and claims.get('role') != 'admin':
        return jsonify({"error": "Não tem permissão para ver o progresso desta tarefa."}), 403
    
    status_rq = job.get_status()
    progress_data = job.meta.copy()

    if status_rq == 'finished' and 'result' in job.meta:
        progress_data['status'] = 'completed'
        progress_data['result'] = job.meta['result']
        progress_data['pdf_path'] = job.meta.get('pdf_path')
    elif status_rq == 'queued':
        progress_data['status'] = 'queued'
    elif status_rq == 'started':
        progress_data['status'] = 'processing'
    elif status_rq == 'finished':
        progress_data['status'] = progress_data.get('status', 'completed')
    elif status_rq == 'failed':
        progress_data['status'] = 'error'
    
    if progress_data.get('total_steps', 0) == 0:
        progress_data['total_steps'] = 1
    
    progress_data.pop('user_id', None)

    return jsonify(progress_data)

@app.route('/api/download/<task_id>', methods=['GET'])
@jwt_required()
def download_result(task_id):
    current_user_id = get_jwt_identity()
    job = None
    for q in QUEUES.values():
        job = q.fetch_job(task_id)
        if job: break
    if not job:
        return jsonify({'error': 'Tarefa não encontrada'}), 404
    claims = get_jwt()
    if job.meta.get('user_id') != current_user_id and claims.get('role') != 'admin':
        return jsonify({"error": "Não tem permissão para descarregar o resultado desta tarefa."}), 403
    if job.get_status() != 'finished' or job.meta.get('status') != 'completed':
        return jsonify({'error': 'A tarefa ainda não foi concluída ou falhou'}), 400
    file_path = job.meta.get('file_path')
    filename = job.meta.get('filename')
    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'Ficheiro de resultado não encontrado ou já removido'}), 404
    mimetype = 'text/csv'
    def remove_file_after_download():
        time.sleep(5)
        try:
            os.unlink(file_path)
        except Exception as e:
            print(f"Erro ao remover ficheiro: {e}")
    cleanup_thread = threading.Thread(target=remove_file_after_download)
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

if __name__ == '__main__':
    from auth_service import create_tables
    with app.app_context():
        create_tables()
    app.run(host='0.0.0.0', port=5000, debug=False)
