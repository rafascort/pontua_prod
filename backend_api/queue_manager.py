# /opt/pontua/AutoPonto/backend_api/queue_manager.py
import os
import tempfile
from datetime import datetime
import redis
from rq import Queue
import threading
import time
import traceback
import stripe
import payroll_extractor_ai

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from dotenv import load_dotenv

# Importa o app e o db do auth_service
from auth_service import app as auth_app, db, User, jwt as auth_jwt, admin_required

load_dotenv()

app = auth_app
CORS(app, resources={r"/api/*": {"origins": ["http://localhost:3000", "https://sistemaponto.com", "https://sistemaponto.com.br"]}}, supports_credentials=True)

app.secret_key = os.getenv('FLASK_SECRET_KEY')
redis_conn = redis.Redis(host='localhost', port=6379, db=0)

# --- Configuração Stripe ---
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

# --- LIMITES DOS PLANOS ---
try:
    PLAN_LIMITS = {
        'free':     int(os.getenv('PLAN_LIMIT_FREE',    50)),
        'basic':    int(os.getenv('PLAN_LIMIT_BASICO',  200)),
        'standard': int(os.getenv('PLAN_LIMIT_PADRAO',  500)),
        'premium':  int(os.getenv('PLAN_LIMIT_PREMIUM', 1500)),
        'past_due': 0,
        'inactive': 0,
    }
except ValueError:
    print("ERRO CRÍTICO (queue_manager): Limites de plano no .env não são números válidos.")
    PLAN_LIMITS = {'free': 50, 'basic': 200, 'standard': 500, 'premium': 1500, 'past_due': 0, 'inactive': 0}

# Planos pagos que podem usar páginas extras (cobradas pelo Stripe)
PAID_PLANS = ['basic', 'standard', 'premium']

# Mapeamento de nome de plano para ID DE PREÇO DE PÁGINA EXTRA
PLAN_NAME_TO_EXTRA_PRICE_ID = {
    'basic':    os.getenv('STRIPE_PRICE_ID_BASICO_EXTRA'),
    'standard': os.getenv('STRIPE_PRICE_ID_PADRAO_EXTRA'),
    'premium':  os.getenv('STRIPE_PRICE_ID_PREMIUM_EXTRA'),
}
if not all(k for k in PLAN_NAME_TO_EXTRA_PRICE_ID.values() if k):
    print("\n\n*** AVISO (queue_manager): IDs de preço EXTRA (STRIPE_PRICE_ID_*_EXTRA) não encontrados no .env! Cobrança de extras não funcionará. ***\n\n")


# --- FILAS ---
QUEUES = {
    '6':               Queue('geral_ai_queue',        connection=redis_conn),
    '7':               Queue('geral_queue',            connection=redis_conn),
    'payroll':         Queue('payroll_queue',          connection=redis_conn),
    'period_extraction': Queue('period_extraction_queue', connection=redis_conn),
}

EXTRACTOR_MODULES = {
    '6':               'extractor_geral_ai',
    '7':               'extractor_geral',
    'payroll':         'payroll_extractor_ai',
    'period_extraction': 'extractor_geral_ai',
}


# =============================================================
# CORREÇÃO: check_user_page_balance
# Valida saldo server-side antes de enfileirar qualquer job.
#
# REGRA:
#   - Admin         → sempre liberado
#   - Plano pago    → sempre liberado (extras cobráveis pelo Stripe)
#   - Free trial    → bloqueado quando saldo = 0 ou insuficiente
# =============================================================
def check_user_page_balance(user_email: str, pages_requested: int):
    """
    Verifica se o usuário pode processar a quantidade de páginas solicitada.

    Retorna:
        (True, None)            → pode processar
        (False, (json, status)) → bloqueia com resposta de erro
    """
    # 0 = "todas as páginas do PDF" — worker calculará o total real no /download.
    if pages_requested <= 0:
        return True, None

    user = User.query.filter_by(email=user_email).first()
    if not user:
        return False, (jsonify({"error": "Usuário não encontrado."}), 404)

    # Admin não tem limite de páginas
    if user.role == 'admin':
        return True, None

    plan_status = user.plan_status or 'free'

    # CORREÇÃO: planos pagos sempre podem processar — quando ultrapassam o
    # limite incluído, as páginas extras são cobradas automaticamente pelo Stripe.
    if plan_status in PAID_PLANS:
        return True, None

    # Free trial: bloqueia quando saldo = 0 ou insuficiente
    plan_limit    = PLAN_LIMITS.get(plan_status, 0)
    current_count = user.page_count or 0
    balance       = plan_limit - current_count

    if balance <= 0:
        return False, (
            jsonify({
                "error":       "Saldo de páginas esgotado.",
                "detail":      "Suas páginas grátis foram utilizadas. "
                               "Assine um plano para continuar.",
                "balance":     0,
                "plan_status": plan_status,
            }),
            403,
        )

    if pages_requested > balance:
        return False, (
            jsonify({
                "error":           "Páginas insuficientes.",
                "detail":          f"Você solicitou {pages_requested} página(s) mas tem apenas "
                                   f"{balance} disponível(is) no plano gratuito.",
                "balance":         balance,
                "pages_requested": pages_requested,
                "plan_status":     plan_status,
            }),
            403,
        )

    return True, None


# =============================================================
# FUNÇÃO PARA REPORTAR USO (BILLING METERS)
# =============================================================
def report_usage_to_stripe(user, pages_processed_this_job, new_total_page_count):
    """
    Reporta o uso de páginas para o Stripe usando Billing Meters (Stripe 13.x).
    Só reporta páginas que ultrapassaram o limite do plano (extras cobráveis).
    """
    print(f"[DIAGNOSTICO] Iniciando 'report_usage_to_stripe' para {user.email if user else 'N/A'}...")

    if not user or not user.stripe_customer_id:
        print(f"[ERRO] Usuário {user.email if user else 'N/A'} não possui stripe_customer_id.")
        return

    if not user.plan_status or user.plan_status == 'free' or user.role == 'admin':
        print(f"[DIAGNOSTICO] Usuário {user.email} não é elegível para reporte (Plano: {user.plan_status}, Role: {user.role}).")
        return

    plan_limit     = PLAN_LIMITS.get(user.plan_status)
    extra_price_id = PLAN_NAME_TO_EXTRA_PRICE_ID.get(user.plan_status)

    if plan_limit is None:
        print(f"AVISO: Limite não definido para plano '{user.plan_status}' ({user.email}). Não reportando uso.")
        return

    if not extra_price_id:
        print(f"AVISO: Preço extra não definido para plano '{user.plan_status}' ({user.email}). Não reportando uso.")
        return

    previous_page_count = new_total_page_count - pages_processed_this_job
    pages_to_report     = max(0, new_total_page_count - max(previous_page_count, plan_limit))

    print(f"[DIAGNOSTICO] Cálculo: Total={new_total_page_count}, Anterior={previous_page_count}, "
          f"Adicionadas={pages_processed_this_job}, Limite={plan_limit}, A_Reportar={pages_to_report}")

    if pages_to_report > 0:
        print(f"REPORTANDO USO (Billing Meter): User {user.email} usou +{pages_to_report} pgs extras.")
        try:
            event_name  = "pagina_extra"
            meter_event = stripe.billing.MeterEvent.create(
                event_name=event_name,
                payload={
                    "value":              str(pages_to_report),
                    "stripe_customer_id": user.stripe_customer_id,
                }
            )
            print(f"SUCESSO: Reportado {pages_to_report} pgs extras para {user.email} "
                  f"via Meter '{event_name}' (Event ID: {meter_event.identifier}).")
        except stripe.StripeError as e:
            print(f"ERRO STRIPE ao reportar uso (Meter) para {user.email}: {getattr(e, 'user_message', str(e))}")
            traceback.print_exc()
        except Exception as e:
            print(f"ERRO INESPERADO ao reportar uso (Meter) para {user.email}: {e}")
            traceback.print_exc()
    else:
        print(f"[DIAGNOSTICO] Nenhuma página extra para reportar (pages_to_report={pages_to_report}).")


# =============================================================
# ROTAS DE FOLHA DE PAGAMENTO
# CORREÇÃO: removido @admin_required() — qualquer usuário ativo
# com plano pode usar o extrator de holerite.
# =============================================================

@app.route('/api/payroll/analyze', methods=['POST'])
@jwt_required()
def payroll_analyze():
    current_user_email = get_jwt_identity()
    claims = get_jwt()
    if claims.get('is_active') == False:
        return jsonify({"error": "Conta inativa."}), 403
 
    if 'pdf_file' not in request.files:
        return jsonify({'error': 'PDF não enviado.'}), 400
 
    file  = request.files['pdf_file']
    pages = request.form.get('pages', '')
 
    # Verifica saldo antes de enfileirar
    if pages:
        pages_requested = sum(
            (int(p.split('-')[1]) - int(p.split('-')[0]) + 1)
            if '-' in p else 1
            for p in pages.replace(' ', '').split(',')
            if p and (p.isdigit() or ('-' in p and all(x.isdigit() for x in p.split('-') if x)))
        )
        can_process, error_response = check_user_page_balance(current_user_email, pages_requested)
        if not can_process:
            return error_response
 
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        file.save(tmp.name)
        pdf_path = tmp.name
 
    q   = QUEUES.get('payroll')
    job = q.enqueue(
        'payroll_extractor_ai.scan_verbas_task',
        pdf_path, pages, current_user_email,
        job_timeout='30m', result_ttl=1800,
        meta={'user_id': current_user_email, 'step': 'payroll_analysis'}
    )
    return jsonify({'task_id': job.id})


@app.route('/api/payroll/process', methods=['POST'])
@jwt_required()
def payroll_process():
    current_user_email = get_jwt_identity()
    claims = get_jwt()
    if claims.get('is_active') == False:
        return jsonify({"error": "Conta inativa."}), 403
 
    data  = request.get_json()
    pages = data.get('pages', '')
 
    # Verifica saldo antes de enfileirar
    if pages:
        pages_requested = sum(
            (int(p.split('-')[1]) - int(p.split('-')[0]) + 1)
            if '-' in p else 1
            for p in pages.replace(' ', '').split(',')
            if p and (p.isdigit() or ('-' in p and all(x.isdigit() for x in p.split('-') if x)))
        )
        can_process, error_response = check_user_page_balance(current_user_email, pages_requested)
        if not can_process:
            return error_response
 
    q   = QUEUES.get('payroll')
    job = q.enqueue(
        'payroll_extractor_ai.process_payroll_final_task',
        data['pdf_path'], pages, data['selected_verbas'], current_user_email,
        job_timeout='1h', result_ttl=1800,
        meta={'user_id': current_user_email, 'usage_counted': False}
    )
    return jsonify({'task_id': job.id}) 

# =============================================================
# ROTA: /api/extract-periods
# Primeira etapa do extrator de ponto (identificação de períodos).
# =============================================================
@app.route('/api/extract-periods', methods=['POST'])
@jwt_required()
def extract_periods():
    current_user_email = get_jwt_identity()
    claims = get_jwt()
    if claims.get('is_active') == False:
        return jsonify({"error": "Conta inativa."}), 403

    pdf_path = None
    try:
        if 'pdf_file' not in request.files:
            return jsonify({'error': 'PDF não enviado.'}), 400
        file  = request.files['pdf_file']
        pages = request.form.get('pages', '')
        if file.filename == '':
            return jsonify({'error': 'Nenhum ficheiro selecionado.'}), 400

        # Valida se o usuário pode processar pelo menos 1 página
        ok, err = check_user_page_balance(current_user_email, 1)
        if not ok:
            return err

        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            file.save(tmp_file.name)
            pdf_path = tmp_file.name

        q = QUEUES.get('period_extraction')
        if not q:
            raise ValueError("Fila 'period_extraction' não encontrada.")

        job = q.enqueue(
            'extractor_geral_ai.extract_periods_task',
            pdf_path, pages,
            user_id=current_user_email,
            job_timeout='2m', result_ttl=1800,
            meta={'user_id': current_user_email, 'pdf_path': pdf_path, 'step': 'period_extraction'}
        )
        return jsonify({'task_id': job.id, 'status': 'queued', 'step': 'period_extraction'})

    except Exception as e:
        print(f"Erro /extract-periods: {e}")
        traceback.print_exc()
        if pdf_path and os.path.exists(pdf_path):
            try:
                os.unlink(pdf_path)
            except Exception as unlink_e:
                print(f"Erro ao remover {pdf_path}: {unlink_e}")
        return jsonify({'error': 'Erro interno análise.'}), 500


# =============================================================
# ROTA: /api/process  (Modelo "Com Data" — fluxo com períodos)
# =============================================================
@app.route('/api/process', methods=['POST'])
@jwt_required()
def process_pdf():
    current_user_email = get_jwt_identity()
    claims = get_jwt()
    if claims.get('is_active') == False:
        return jsonify({"error": "Conta inativa."}), 403

    num_pages_to_process = 0
    pdf_path = None
    try:
        data               = request.get_json()
        pages_with_periods = data.get('pages_with_periods')
        pdf_path           = data.get('pdf_path')
        model_type         = data.get('model_type', '6')

        if not pages_with_periods or not pdf_path:
            return jsonify({'error': 'Dados incompletos.'}), 400
        if not os.path.exists(pdf_path):
            return jsonify({'error': f'PDF não encontrado: {pdf_path}. Inicie novamente.'}), 404
        if model_type != '6':
            return jsonify({'error': f'Modelo inválido ({model_type}).'}), 400
        if model_type not in QUEUES or model_type not in EXTRACTOR_MODULES:
            return jsonify({'error': 'Modelo não configurado.'}), 400

        num_pages_to_process = len(pages_with_periods)

        ok, err = check_user_page_balance(current_user_email, num_pages_to_process)
        if not ok:
            return err

        q                     = QUEUES.get(model_type)
        extractor_module_name = EXTRACTOR_MODULES.get(model_type)
        if not q or not extractor_module_name:
            raise ValueError(f"Fila/Módulo não encontrado para modelo {model_type}.")

        job = q.enqueue(
            f'{extractor_module_name}.process_pdf_task',
            pdf_path, pages_with_periods, model_type,
            user_id=current_user_email,
            job_timeout='1h', result_ttl=1800,
            meta={
                'user_id':          current_user_email,
                'step':             'full_processing',
                'pages_to_process': num_pages_to_process,
                'usage_counted':    False,
            }
        )
        return jsonify({'task_id': job.id, 'status': 'queued', 'step': 'full_processing'})

    except Exception as e:
        print(f"Erro /process: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Erro interno ao processar.'}), 500


# =============================================================
# ROTA: /api/process-direct  (Modelo "Sem Data" — direto)
# =============================================================
@app.route('/api/process-direct', methods=['POST'])
@jwt_required()
def process_pdf_direct():
    current_user_email = get_jwt_identity()
    claims = get_jwt()
    if claims.get('is_active') == False:
        return jsonify({"error": "Conta inativa."}), 403

    num_pages_to_process = 0
    pdf_path = None
    try:
        if 'pdf_file' not in request.files:
            return jsonify({'error': 'PDF não enviado.'}), 400
        file       = request.files['pdf_file']
        pages      = request.form.get('pages', '')
        model_type = '7'

        if file.filename == '':
            return jsonify({'error': 'Nenhum ficheiro selecionado.'}), 400

        if model_type not in QUEUES or model_type not in EXTRACTOR_MODULES:
            raise ValueError(f'Modelo {model_type} não configurado.')

        if pages:
            page_list = []
            for part in pages.split(','):
                part = part.strip()
                if '-' in part:
                    try:
                        start, end = map(int, part.split('-'))
                        page_list.extend(range(start, end + 1))
                    except ValueError:
                        pass
                elif part.isdigit():
                    page_list.append(int(part))
            num_pages_to_process = len(set(p for p in page_list if p > 0))
        else:
            num_pages_to_process = 0

        if num_pages_to_process > 0:
            ok, err = check_user_page_balance(current_user_email, num_pages_to_process)
            if not ok:
                return err

        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            file.save(tmp_file.name)
            pdf_path = tmp_file.name

        q                     = QUEUES.get(model_type)
        extractor_module_name = EXTRACTOR_MODULES.get(model_type)
        if not q or not extractor_module_name:
            raise ValueError(f"Fila/Módulo não encontrado para modelo {model_type}.")

        job = q.enqueue(
            f'{extractor_module_name}.process_pdf_task',
            pdf_path, pages, model_type,
            user_id=current_user_email,
            job_timeout='2h', result_ttl=1800,
            meta={
                'user_id':          current_user_email,
                'step':             'full_processing',
                'pages_to_process': num_pages_to_process,
                'usage_counted':    False,
            }
        )
        return jsonify({'task_id': job.id, 'status': 'queued'})

    except Exception as e:
        print(f"Erro /process-direct: {e}")
        traceback.print_exc()
        if pdf_path and os.path.exists(pdf_path):
            try:
                os.unlink(pdf_path)
            except Exception as unlink_e:
                print(f"Erro ao remover {pdf_path}: {unlink_e}")
        return jsonify({'error': 'Erro interno ao processar.'}), 500


# =============================================================
# ROTA: /api/progress/<task_id>
# =============================================================
@app.route('/api/progress/<task_id>', methods=['GET'])
@jwt_required()
def get_progress(task_id):
    current_user_email = get_jwt_identity()
    job = None
    try:
        for q_name, q in QUEUES.items():
            job = q.fetch_job(task_id)
            if job:
                break
    except Exception as e:
        print(f"Erro ao buscar job {task_id} nas filas: {e}")
        return jsonify({'error': 'Erro interno ao buscar tarefa.'}), 500

    if not job:
        print(f"Job {task_id} não encontrado em nenhuma fila conhecida.")
        return jsonify({'error': 'Tarefa não encontrada ou expirada'}), 404

    claims      = get_jwt()
    job_user_id = job.meta.get('user_id')
    if str(job_user_id) != str(current_user_email) and claims.get('role') != 'admin':
        print(f"Acesso negado: User {current_user_email} job {task_id} de {job_user_id}")
        return jsonify({"error": "Sem permissão."}), 403

    status_rq     = job.get_status()
    progress_data = job.meta.copy()

    if status_rq == 'finished':
        internal_status         = progress_data.get('status', 'completed')
        progress_data['status'] = internal_status
        if internal_status == 'completed':
            progress_data['result'] = job.result
        elif internal_status == 'error':
            progress_data['error']  = job.meta.get('error', 'Erro interno.')
    elif status_rq == 'queued':
        progress_data['status'] = 'queued'
        progress_data.setdefault('message', 'Na fila...')
    elif status_rq == 'started':
        progress_data['status'] = 'processing'
        progress_data.setdefault('message', 'Processando...')
    elif status_rq == 'failed':
        progress_data['status'] = 'error'
        exc_info = job.exc_info
        progress_data['error'] = exc_info.strip().split('\n')[-1] if exc_info else job.meta.get('error', 'Falhou.')
    else:
        progress_data['status'] = status_rq
        progress_data.setdefault('message', f'Status: {status_rq}')

    progress_data.setdefault('current_step', 0)
    progress_data.setdefault('total_steps',  1)
    if progress_data['total_steps'] == 0:
        progress_data['total_steps'] = 1
    progress_data.pop('user_id', None)

    return jsonify(progress_data)


# =============================================================
# ROTA: /api/download/<task_id>
# Contabiliza o uso de páginas e reporta extras ao Stripe.
# =============================================================
@app.route('/api/download/<task_id>', methods=['GET'])
@jwt_required()
def download_result(task_id):
    current_user_email = get_jwt_identity()

    job = None
    for q in QUEUES.values():
        try:
            job = q.fetch_job(task_id)
        except Exception as e:
            print(f"Erro buscar job {task_id} fila {q.name}: {e}")
            continue
        if job:
            break

    if not job:
        return jsonify({'error': 'Tarefa não encontrada/expirada'}), 404

    claims      = get_jwt()
    job_user_id = job.meta.get('user_id')
    if str(job_user_id) != str(current_user_email) and claims.get('role') != 'admin':
        return jsonify({"error": "Sem permissão."}), 403

    if job.get_status() != 'finished' or job.meta.get('status') != 'completed':
        return jsonify({'error': 'Tarefa não concluiu com sucesso.'}), 400

    file_path = job.meta.get('file_path')
    filename  = job.meta.get('filename')
    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'Ficheiro resultado não encontrado.'}), 404

    # ─── Contabilização de uso (executa apenas uma vez por job) ──────────
    if not job.meta.get('usage_counted', False):
        print(f"[LOG] Job {task_id} será contabilizado agora (antes do download)...")
        try:
            num_pages_processed  = int(job.meta.get('pages_to_process', 0))
            user = User.query.filter_by(email=current_user_email).first()

            if user and user.role != 'admin' and num_pages_processed > 0:
                user.page_count     += num_pages_processed
                new_total_page_count = user.page_count
                db.session.commit()

                print(f"[LOG] Páginas CONTADAS (no download) para {current_user_email}: "
                      f"+{num_pages_processed} (Total: {new_total_page_count})")

                report_usage_to_stripe(user, num_pages_processed, new_total_page_count)

                job.meta['usage_counted'] = True
                job.save_meta()

            elif user:
                print(f"[LOG] Usuário {current_user_email} é admin ou 0 páginas — contagem não aplicada.")
                job.meta['usage_counted'] = True
                job.save_meta()
            else:
                print(f"[ERRO] Usuário {current_user_email} não encontrado no DB para contagem.")

        except Exception as e:
            db.session.rollback()
            print(f"[ERRO FATAL] Contagem/Reporte falhou para {current_user_email} no /download: {e}")
            traceback.print_exc()
    else:
        print(f"[LOG] Job {task_id} já teve uso contabilizado. Apenas enviando arquivo.")
    # ─────────────────────────────────────────────────────────────────────

    def remove_file_after_download(path_to_remove):
        time.sleep(10)
        try:
            os.unlink(path_to_remove)
            print(f"Ficheiro {path_to_remove} removido (job {task_id}).")
        except Exception as e:
            print(f"Erro ao remover {path_to_remove} (job {task_id}): {e}")

    cleanup_thread        = threading.Thread(target=remove_file_after_download, args=(file_path,))
    cleanup_thread.daemon = True
    cleanup_thread.start()

    try:
        return send_file(file_path, mimetype='text/csv', as_attachment=True, download_name=filename)
    except Exception as send_e:
        print(f"Erro ao enviar {file_path} (job {task_id}): {send_e}")
        return jsonify({'error': 'Erro ao enviar ficheiro.'}), 500


# =============================================================
# ROTA: /api/health
# =============================================================
@app.route('/api/health', methods=['GET'])
def health_check():
    redis_status = "Unknown"
    db_status    = "Unknown"
    try:
        redis_conn.ping()
        redis_status = "OK"
    except Exception as e:
        redis_status = f"ERROR: {str(e)}"
    try:
        db.session.execute(db.text('SELECT 1'))
        db_status = "OK"
    except Exception as e:
        db_status = f"ERROR: {str(e)}"
    return jsonify({'status': 'OK', 'redis_status': redis_status, 'db_status': db_status})
