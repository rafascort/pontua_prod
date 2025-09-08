# /opt/pontua/AutoPonto/backend_api/queue_manager.py

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import tempfile
import uuid
from datetime import datetime
import redis
from rq import Queue # get_current_job não é necessário aqui, apenas no worker
import threading
import time

app = Flask(__name__)
CORS(app)

# Conexão com o Redis
redis_conn = redis.Redis(host='localhost', port=6379, db=0)

# Mapeamento de queues por model_type
QUEUES = {
    '1': Queue('jbs_queue', connection=redis_conn),
    '2': Queue('brf_queue', connection=redis_conn),
    '3': Queue('pontomais_queue', connection=redis_conn),
    '4': Queue('minuano_queue', connection=redis_conn),
}

# Mapeamento para o módulo de lógica de extração
EXTRACTOR_MODULES = {
    '1': 'extractor_jbs',
    '2': 'extractor_brf',
    '3': 'extractor_pontomais',
    '4': 'extractor_minuano',
}

@app.route('/process', methods=['POST'])
def process_pdf():
    """Endpoint para enfileirar o processamento de PDF."""
    try:
        if 'pdf_file' not in request.files:
            return jsonify({'error': 'Nenhum arquivo PDF foi enviado'}), 400
        
        file = request.files['pdf_file']
        pages = request.form.get('pages', '')
        model_type = request.form.get('model_type', '1')

        if file.filename == '':
            return jsonify({'error': 'Nenhum arquivo selecionado'}), 400
        
        if model_type not in QUEUES:
            return jsonify({'error': f'Tipo de modelo {model_type} inválido ou não configurado.'}), 400

        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            file.save(tmp_file.name)
            pdf_path = tmp_file.name
        
        q = QUEUES[model_type]
        extractor_module_name = EXTRACTOR_MODULES[model_type]
        
        # --- AQUI ESTÁ A LINHA CRÍTICA: NÃO PASSE 'job' COMO ARGUMENTO ---
        # A função 'process_pdf_task' obterá seu próprio objeto job usando get_current_job()
        job = q.enqueue(f'{extractor_module_name}.process_pdf_task', 
                        pdf_path, pages, model_type, # Argumentos para process_pdf_task
                        job_timeout='1h',
                        meta={
                            'progress': 0,
                            'message': 'Tarefa enfileirada, aguardando processamento...',
                            'status': 'queued',
                            'current_step': 0,
                            'total_steps': 1,
                            'timestamp': datetime.now().isoformat()
                        })
        
        return jsonify({
            'task_id': job.id,
            'message': 'Processamento enfileirado',
            'status': 'queued'
        })
    except Exception as e:
        print(f"Erro ao enfileirar tarefa: {e}")
        return jsonify({'error': f'Erro interno ao enfileirar: {str(e)}'}), 500

@app.route('/progress/<task_id>', methods=['GET'])
def get_progress(task_id):
    """Endpoint para consultar o progresso de uma tarefa."""
    job = None
    for q in QUEUES.values():
        job = q.fetch_job(task_id)
        if job:
            break

    if not job:
        return jsonify({'error': 'Tarefa não encontrada'}), 404

    status_rq = job.get_status()
    progress_data = job.meta.copy()

    if status_rq == 'queued':
        progress_data['status'] = 'queued'
        progress_data['message'] = progress_data.get('message', 'Tarefa na fila, aguardando processamento.')
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

    return jsonify(progress_data)


@app.route('/download/<task_id>', methods=['GET'])
def download_result(task_id):
    """Endpoint para baixar o resultado processado."""
    job = None
    for q in QUEUES.values():
        job = q.fetch_job(task_id)
        if job:
            break

    if not job:
        return jsonify({'error': 'Tarefa não encontrada'}), 404

    if job.get_status() != 'finished' or job.meta.get('status') != 'completed':
        return jsonify({'error': 'Tarefa ainda não foi concluída ou falhou'}), 400

    file_path = job.meta.get('file_path')
    filename = job.meta.get('filename')

    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'Arquivo de resultado não encontrado ou já removido'}), 404

    def remove_file_after_download():
        time.sleep(5)
        try:
            os.unlink(file_path)
            print(f"Arquivo temporário {file_path} removido.")
        except Exception as e:
            print(f"Erro ao remover arquivo temporário {file_path}: {e}")
        
    cleanup_thread = threading.Thread(target=remove_file_after_download)
    cleanup_thread.daemon = True
    cleanup_thread.start()

    return send_file(
        file_path,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint para verificar a saúde do serviço."""
    try:
        redis_conn.ping()
        redis_status = "OK"
    except Exception as e:
        redis_status = f"ERROR: {str(e)}"

    return jsonify({
        'status': 'OK',
        'message': 'Serviço de Gerenciamento de Fila funcionando',
        'redis_status': redis_status
    })

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)

