# /opt/pontua/AutoPonto/backend_api/queue_manager.py
from flask import Flask, request, jsonify, send_file, session
from flask_cors import CORS
import os
import tempfile
import uuid
from datetime import datetime
import redis
from rq import Queue
import threading
import time

from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from dotenv import load_dotenv
from auth_service import app as auth_app, db, User, jwt as auth_jwt, admin_required, create_tables

load_dotenv() # Carrega variáveis de ambiente do .env

app = auth_app
CORS(app, resources={r"/api/*": {"origins": [
    "http://localhost:3000",
    "https://sistemaponto.com",
    "https://sistemaponto.com.br"
]}}, supports_credentials=True)

app.secret_key = os.getenv('FLASK_SECRET_KEY')

redis_conn = redis.Redis(host='localhost', port=6379, db=0)

QUEUES = {
    '1': Queue('jbs_queue', connection=redis_conn),
    '2': Queue('brf_queue', connection=redis_conn),
    '3': Queue('pontomais_queue', connection=redis_conn),
    '4': Queue('minuano_queue', connection=redis_conn),
    '5': Queue('rudder_queue', connection=redis_conn), # ADICIONADO
}

EXTRACTOR_MODULES = {
    '1': 'extractor_jbs',
    '2': 'extractor_brf',
    '3': 'extractor_pontomais',
    '4': 'extractor_minuano',
    '5': 'extractor_rudder', # ADICIONADO
}

@app.route('/api/process', methods=['POST'])
@jwt_required()
def process_pdf():
    current_user_id = get_jwt_identity()
    claims = get_jwt()
    if not claims.get('is_active'):
        return jsonify({"error": "A sua conta está inativa e não pode iniciar processos."}), 403
    try:
        if 'pdf_file' not in request.files:
            return jsonify({'error': 'Nenhum ficheiro PDF foi enviado'}), 400
        file = request.files['pdf_file']
        pages = request.form.get('pages', '')
        model_type = request.form.get('model_type', '1')
        if file.filename == '':
            return jsonify({'error': 'Nenhum ficheiro selecionado'}), 400
        if model_type not in QUEUES:
            return jsonify({'error': f'Tipo de modelo {model_type} inválido ou não configurado.'}), 400
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            file.save(tmp_file.name)
            pdf_path = tmp_file.name
        q = QUEUES[model_type]
        extractor_module_name = EXTRACTOR_MODULES[model_type]
        job = q.enqueue(f'{extractor_module_name}.process_pdf_task',
                        pdf_path, pages, model_type, user_id=current_user_id,
                        job_timeout='1h',
                        meta={
                            'progress': 0, 'message': 'Tarefa na fila, a aguardar processamento...',
                            'status': 'queued', 'current_step': 0, 'total_steps': 1,
                            'timestamp': datetime.now().isoformat(), 'user_id': current_user_id
                        })
        return jsonify({'task_id': job.id, 'message': 'Processamento na fila', 'status': 'queued'})
    except Exception as e:
        print(f"Erro ao colocar tarefa na fila: {e}")
        return jsonify({'error': f'Erro interno ao colocar na fila: {str(e)}'}), 500

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
    if status_rq == 'queued':
        progress_data['status'] = 'queued'
        progress_data['message'] = progress_data.get('message', 'Tarefa na fila, a aguardar processamento.')
    elif status_rq == 'started':
        progress_data['status'] = 'processing'
        progress_data['message'] = progress_data.get('message', 'Processamento iniciado...')
    elif status_rq == 'finished':
        progress_data['status'] = progress_data.get('status', 'completed')
        progress_data['message'] = progress_data.get('message', 'Processamento concluído.')
    elif status_rq == 'failed':
        progress_data['status'] = 'error'
        progress_data['message'] = progress_data.get('error', 'Erro desconhecido durante o processamento.')
        progress_data['progress'] = 0
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
    def remove_file_after_download():
        time.sleep(5)
        try:
            os.unlink(file_path)
            print(f"Ficheiro de resultado {file_path} removido após download.")
        except Exception as e:
            print(f"Erro ao remover ficheiro de resultado {file_path}: {e}")
    cleanup_thread = threading.Thread(target=remove_file_after_download)
    cleanup_thread.daemon = True
    cleanup_thread.start()
    return send_file(file_path, mimetype='text/csv', as_attachment=True, download_name=filename)

@app.route('/api/health', methods=['GET'])
def health_check():
    try:
        redis_conn.ping()
        redis_status = "OK"
    except Exception as e:
        redis_status = f"ERROR: {str(e)}"
    return jsonify({
        'status': 'OK',
        'message': 'Serviço de Gestão de Filas a funcionar',
        'redis_status': redis_status
    })

if __name__ == '__main__':
    with app.app_context():
        create_tables()
    app.run(host='0.0.0.0', port=5000, debug=True)


