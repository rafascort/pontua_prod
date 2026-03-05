# /opt/pontua/AutoPonto/backend_api/auth_service.py
from flask import Flask, request, jsonify, redirect, session, url_for, g
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required, JWTManager, get_jwt
from werkzeug.exceptions import BadRequest
from datetime import datetime, timedelta, date # Adicionado datetime e date
import os
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
import requests
import re
import traceback
from functools import wraps
import stripe
import time # <-- Import time

# Carrega variáveis de ambiente
load_dotenv()

app = Flask(__name__)

# --- Configurações ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES_HOURS', '24')))
app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.getenv('GOOGLE_CLIENT_SECRET')
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
app.config['FLASK_APP'] = 'auth_service.py'

# --- Inicializações ---
jwt = JWTManager(app)
oauth = OAuth(app)
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# --- Configuração Google OAuth ---
google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    access_token_url='https://accounts.google.com/o/oauth2/token',
    access_token_params=None,
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    authorize_params=None,
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    userinfo_endpoint='https://openidconnect.googleapis.com/v1/userinfo',
    client_kwargs={'scope': 'openid email profile'},
    jwks_uri='https://www.googleapis.com/oauth2/v3/certs',
)

# --- Configuração Stripe ---
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
if not stripe.api_key:
    print("\n\n*** AVISO CRÍTICO: STRIPE_SECRET_KEY não definida no .env! Pagamentos não funcionarão. ***\n\n")

# Mapeamento de IDs de Preço Fixo para nomes de plano
PRICE_ID_TO_PLAN_NAME = {
    os.getenv('STRIPE_PRICE_ID_BASICO_FIXO'): 'basic',
    os.getenv('STRIPE_PRICE_ID_PADRAO_FIXO'): 'standard',
    os.getenv('STRIPE_PRICE_ID_PREMIUM_FIXO'): 'premium',
}
if not all(k for k in PRICE_ID_TO_PLAN_NAME.keys() if k):
     print("\n\n*** AVISO (auth_service): Pelo menos um ID de preço FIXO do Stripe (STRIPE_PRICE_ID_*) não foi encontrado no .env! ***\n\n")

# --- COPIAR CONFIGS DE USO DE queue_manager.py ---
try:
    PLAN_LIMITS = {
        'free': int(os.getenv('PLAN_LIMIT_FREE', 0)),
        'basic': int(os.getenv('PLAN_LIMIT_BASICO', 200)),
        'standard': int(os.getenv('PLAN_LIMIT_PADRAO', 500)),
        'premium': int(os.getenv('PLAN_LIMIT_PREMIUM', 1500)),
        'past_due': 0, 'inactive': 0
    }
except ValueError:
    print("ERRO CRÍTICO (auth_service): Limites de plano no .env não são números válidos.")
    PLAN_LIMITS = {'free': 0, 'basic': 200, 'standard': 500, 'premium': 1500, 'past_due': 0, 'inactive': 0}

PLAN_NAME_TO_EXTRA_PRICE_ID = {
    'basic': os.getenv('STRIPE_PRICE_ID_BASICO_EXTRA'),
    'standard': os.getenv('STRIPE_PRICE_ID_PADRAO_EXTRA'),
    'premium': os.getenv('STRIPE_PRICE_ID_PREMIUM_EXTRA'),
}
if not all(k for k in PLAN_NAME_TO_EXTRA_PRICE_ID.values() if k):
     print("\n\n*** AVISO (auth_service): IDs de preço EXTRA (STRIPE_PRICE_ID_*_EXTRA) não encontrados no .env! Cobrança de extras não funcionará. ***\n\n")
# --- FIM COPIAR CONFIGS ---


# --- Modelos do Banco de Dados ---
class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=True)
    role = db.Column(db.String(50), nullable=False, default='user')
    is_active = db.Column(db.Boolean, default=True)
    page_count = db.Column(db.Integer, default=0)
    plan_status = db.Column(db.String(50), nullable=False, default='free')
    stripe_customer_id = db.Column(db.String(120), nullable=True, unique=True)
    next_reset_date = db.Column(db.Date, nullable=True)


# --- Funções Auxiliares JWT e Decorators ---

@jwt.additional_claims_loader
def add_claims_to_access_token(identity):
    user = User.query.filter_by(email=identity).first()
    if user:
        return {
            'role': user.role,
            'is_active': user.is_active,
            'plan_status': user.plan_status or 'free',
            'user_id': user.id
        }
    return {}

def admin_required():
    def wrapper(fn):
        @wraps(fn)
        @jwt_required()
        def decorator(*args, **kwargs):
            claims = get_jwt()
            if claims.get('role') == 'admin':
                return fn(*args, **kwargs)
            else:
                return jsonify(msg="Acesso restrito a administradores!"), 403
        return decorator
    return wrapper

@jwt.token_in_blocklist_loader
def check_if_token_in_blocklist(jwt_header, jwt_payload):
    return False

# --- Rotas de Autenticação e Usuário ---
@app.route('/api/login', methods=['POST'])
def login():
    email = request.json.get('email', None)
    password = request.json.get('password', None)
    if not email or not password:
        return jsonify({"msg": "Email e senha são obrigatórios"}), 400
    user = User.query.filter_by(email=email).first()
    if user and user.password_hash:
        try:
            if check_password_hash(user.password_hash, password):
                if not user.is_active:
                    return jsonify({"msg": "Sua conta está inativa. Entre em contato com o suporte."}), 403
                if user.stripe_customer_id and not user.next_reset_date:
                    print(f"[LOGIN SYNC] Corrigindo data de reset para {user.email}...")
                    sync_user_billing_cycle(user.email)
                access_token = create_access_token(identity=email)
                return jsonify(access_token=access_token), 200
            else:
                 return jsonify({"msg": "Email ou senha inválidos"}), 401
        except ValueError as e:
            print(f"Erro ao verificar hash para {email}: {e}")
            return jsonify({"msg": "Erro interno ao verificar senha. Contate o suporte."}), 500
    elif user and not user.password_hash:
        return jsonify({"msg": "Login com senha não disponível. Use o login com Google."}), 401
    else:
        return jsonify({"msg": "Email ou senha inválidos"}), 401

@app.route('/api/register', methods=['POST'])
def register():
    email = request.json.get('email', None)
    password = request.json.get('password', None)
    name = request.json.get('name', None)
    if not email or not password:
        return jsonify({"msg": "Email e senha são obrigatórios"}), 400
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
         return jsonify({"msg": "Formato de e-mail inválido"}), 400
    if len(password) < 6: return jsonify({"msg": "Senha precisa ter pelo menos 6 caracteres"}), 400
    if not re.search(r"\d", password): return jsonify({"msg": "Senha precisa ter pelo menos 1 número"}), 400
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password): return jsonify({"msg": "Senha precisa ter pelo menos 1 caractere especial"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "Email já cadastrado"}), 409

    hashed_password = generate_password_hash(password)
    new_user = User(
        email=email,
        password_hash=hashed_password,
        # name=name, # Descomente se adicionar a coluna 'name'
        is_active=True,
        role='user',
        page_count=0,
        plan_status='free'
    )
    db.session.add(new_user)
    try:
        db.session.commit()
        return jsonify({"msg": f"Usuário {email} criado com sucesso! Faça o login."}), 201
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao registrar usuário: {e}")
        return jsonify({"msg": "Erro interno ao criar usuário."}), 500

@app.route('/api/auth/google')
def google_login():
    redirect_uri = url_for('google_authorize', _external=True)
    state = os.urandom(16).hex()
    session['oauth_state'] = state
    return google.authorize_redirect(redirect_uri, state=state)

@app.route('/api/auth/google/callback')
def google_authorize():
    try:
        state = session.pop('oauth_state', None)
        received_state = request.args.get('state')
        if state is None or received_state is None or state != received_state:
             print("Erro de state OAuth")
             return redirect(f"{os.getenv('FRONTEND_URL', '/')}/login?error=InvalidOAuthState")
        token = google.authorize_access_token()
    except Exception as e:
        print(f"Erro ao obter token do Google: {e}")
        return redirect(f"{os.getenv('FRONTEND_URL', '/')}/login?error=FailedToFetchGoogleToken")
    try:
        user_info = google.get('userinfo', token=token)
        user_data = user_info.json()
    except Exception as e:
        print(f"Erro ao obter userinfo do Google: {e}")
        return redirect(f"{os.getenv('FRONTEND_URL', '/')}/login?error=FailedToFetchUserInfo")

    google_email = user_data.get('email')
    if not google_email:
        return redirect(f"{os.getenv('FRONTEND_URL', '/')}/login?error=NoEmailFromGoogle")

    user = User.query.filter_by(email=google_email).first()
    if not user: return redirect(f"{os.getenv('FRONTEND_URL', '/')}/login?error=UserNotFound")
    if not user.is_active: return redirect(f"{os.getenv('FRONTEND_URL', '/')}/login?error=AccountInactive")

    access_token = create_access_token(identity=google_email)
    return redirect(f"{os.getenv('FRONTEND_URL', '/')}/login?token={access_token}")

@app.route('/api/user/me', methods=['GET'])
@jwt_required()
def get_user_details():
    current_user_email = get_jwt_identity()
    user = User.query.filter_by(email=current_user_email).first()
    if not user:
        return jsonify({"msg": "Usuário não encontrado"}), 404
    claims = get_jwt()
    return jsonify(
        id=user.id,
        email=user.email,
        role=claims.get('role', 'user'),
        is_active=claims.get('is_active', False),
        page_count=user.page_count,
        plan_status=claims.get('plan_status', 'free'),
        stripe_customer_id=user.stripe_customer_id
    ), 200

@app.route('/api/user/password', methods=['PUT'])
@jwt_required()
def update_password():
    current_user_email = get_jwt_identity()
    user = User.query.filter_by(email=current_user_email).first()
    if not user: return jsonify({"msg": "Usuário não encontrado"}), 404
    current_password = request.json.get('currentPassword')
    new_password = request.json.get('newPassword')
    if not current_password or not new_password: return jsonify({"msg": "Senha atual e nova senha são obrigatórias"}), 400
    if not user.password_hash: return jsonify({"msg": "Não é possível alterar senha de contas criadas via Google."}), 400
    try:
        if not check_password_hash(user.password_hash, current_password): return jsonify({"msg": "Senha atual incorreta"}), 401
    except ValueError as e:
         print(f"Erro ao verificar hash (update_password) para {current_user_email}: {e}")
         return jsonify({"msg": "Erro interno ao verificar senha. Contate o suporte."}), 500
    if len(new_password) < 6: return jsonify({"msg": "Nova senha precisa ter pelo menos 6 caracteres"}), 400
    if not re.search(r"\d", new_password): return jsonify({"msg": "Nova senha precisa ter pelo menos 1 número"}), 400
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", new_password): return jsonify({"msg": "Nova senha precisa ter pelo menos 1 caractere especial"}), 400

    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    return jsonify({"msg": "Senha atualizada com sucesso"}), 200

# --- ROTAS DE ADMINISTRAÇÃO ---
@app.route('/api/admin/users', methods=['GET'])
@admin_required()
def get_users():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        search_email = request.args.get('search', '', type=str)
        sort_by = request.args.get('sort_by', 'id', type=str)
        sort_order = request.args.get('sort_order', 'asc', type=str)
        filter_plan = request.args.get('filter_plan', '', type=str)
        query = User.query
        if search_email:
            query = query.filter(User.email.ilike(f"%{search_email}%"))
        if filter_plan and filter_plan != 'all':
            if filter_plan == 'free':
                query = query.filter((User.plan_status == None) | (User.plan_status == 'free'))
            else:
                query = query.filter(User.plan_status.ilike(f"%{filter_plan}%"))
        valid_sort_columns = {'id': User.id, 'email': User.email, 'status': User.is_active, 'role': User.role, 'plan': User.plan_status, 'pages': User.page_count}
        sort_column = valid_sort_columns.get(sort_by, User.id)
        if sort_order.lower() == 'desc':
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        users = pagination.items
        return jsonify({"users": [{"id": user.id, "email": user.email, "role": user.role, "is_active": user.is_active, "page_count": user.page_count, "plan_status": user.plan_status or 'free'} for user in users], "total_pages": pagination.pages, "current_page": page, "total_users": pagination.total}), 200
    except Exception as e:
        print(f"Erro ao buscar usuários: {e}")
        traceback.print_exc()
        return jsonify({"msg": "Erro interno ao buscar usuários"}), 500

@app.route('/api/admin/users/<int:user_id>/status', methods=['PUT'])
@admin_required()
def update_user_status(user_id):
    user = User.query.get(user_id)
    if not user: return jsonify({"msg": "Usuário não encontrado"}), 404
    claims = get_jwt()
    current_admin_email = get_jwt_identity()
    if user.email == current_admin_email: return jsonify({"msg": "Não pode alterar o status da sua própria conta."}), 403
    is_active_data = request.json.get('is_active')
    if is_active_data is None or not isinstance(is_active_data, bool): return jsonify({"msg": "Campo 'is_active' (booleano) é obrigatório."}), 400
    user.is_active = is_active_data
    try:
        db.session.commit()
        return jsonify({"msg": f"Status do usuário {user.email} atualizado para {'Ativo' if user.is_active else 'Inativo'}."}), 200
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao atualizar status do usuário {user_id}: {e}")
        return jsonify({"msg": "Erro interno ao salvar alteração de status."}), 500

# --- NOVA FUNÇÃO PARA REPORTAR USO MANUAL (CHAVE DO PAYLOAD CORRIGIDA + LOGS) ---
def report_manual_usage_change(user, added_pages, new_total_page_count):
    """ Reporta ao Stripe APENAS páginas adicionadas manualmente via admin. """
    print(f"[DIAGNOSTICO ADMIN] Iniciando 'report_manual_usage_change' para {user.email}...") # LOG

    if not user:
        print("[DIAGNOSTICO ADMIN] Falha: Objeto 'user' está Nulo.") # LOG
        return
    if not user.stripe_customer_id:
        print(f"[DIAGNOSTICO ADMIN] Falha: 'user.stripe_customer_id' está Nulo ou Vazio para {user.email}.") # LOG
        return
    if not user.plan_status or user.plan_status == 'free':
        print(f"[DIAGNOSTICO ADMIN] Ignorando: Plano '{user.plan_status}' é 'free' ou não definido.") # LOG
        return
    if user.role == 'admin':
        print(f"[DIAGNOSTICO ADMIN] Ignorando: Usuário {user.email} é admin.") # LOG
        return
    if added_pages <= 0:
        print(f"[DIAGNOSTICO ADMIN] Ignorando: Nenhuma página adicionada ({added_pages}).") # LOG
        return

    print(f"[DIAGNOSTICO ADMIN] Usuário {user.email} (Stripe ID: {user.stripe_customer_id}) é elegível para reporte manual.") # LOG
    plan_limit = PLAN_LIMITS.get(user.plan_status)

    if plan_limit is None:
        print(f"[DIAGNOSTICO ADMIN] Falha: Limite não configurado para plano {user.plan_status}.") # LOG
        return

    previous_page_count = new_total_page_count - added_pages
    pages_to_report = max(0, new_total_page_count - max(previous_page_count, plan_limit))

    print(f"[DIAGNOSTICO ADMIN] Cálculo: Total={new_total_page_count}, Anterior={previous_page_count}, Adicionadas={added_pages}, Limite={plan_limit}, A_Reportar={pages_to_report}") # LOG

    if pages_to_report > 0:
        print(f"REPORTANDO USO MANUAL (Medidor): Usuário {user.email} teve {pages_to_report} páginas extras adicionadas.")
        try:
            event_name = "pagina_extra" # Deve corresponder EXATAMENTE ao "Nome do evento" no Stripe

            stripe.billing.MeterEvent.create(
                event_name=event_name,
                payload={
                    "value": pages_to_report,
                    # --- CORREÇÃO DA CHAVE AQUI ---
                    "stripe_customer_id": user.stripe_customer_id
                    # --- FIM DA CORREÇÃO ---
                },
                # timestamp=int(time.time()) # Opcional: Stripe usa o tempo atual se omitido
            )
            print(f"SUCESSO (Admin Edit): Reportado {pages_to_report} páginas extras para o medidor '{event_name}' (Cliente: {user.stripe_customer_id}).")
        except stripe.StripeError as e:
            # LOG detalhado do erro Stripe
            print(f"ERRO STRIPE (Admin Edit) ao reportar uso (Medidor) para {user.email}: {getattr(e, 'user_message', str(e))}")
            traceback.print_exc()
        except Exception as e:
            # LOG detalhado de erro inesperado
            print(f"ERRO INESPERADO (Admin Edit) ao reportar uso (Medidor) para {user.email}: {e}")
            traceback.print_exc()
    else:
        print(f"[DIAGNOSTICO ADMIN] Nenhuma página extra adicionada manualmente para reportar ({pages_to_report}).") # LOG
# --- FIM NOVA FUNÇÃO ---


# --- ROTA DE EDIÇÃO DE USUÁRIO ATUALIZADA ---
@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@admin_required()
def update_user_details(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "Usuário não encontrado"}), 404

    data = request.json
    old_page_count = user.page_count # Guarda a contagem antiga
    page_count_changed = False
    new_page_count = old_page_count

    # Atualizar Email
    if 'email' in data and data['email'] != user.email:
        new_email = data['email']
        if not re.match(r"[^@]+@[^@]+\.[^@]+", new_email): return jsonify({"msg": "Formato de e-mail inválido"}), 400
        existing_user = User.query.filter(User.email == new_email, User.id != user_id).first()
        if existing_user: return jsonify({"msg": "Email já está em uso por outra conta"}), 409
        user.email = new_email

    # Atualizar Role
    if 'role' in data:
         claims = get_jwt()
         current_admin_email = get_jwt_identity()
         if user.email == current_admin_email and data['role'] != 'admin': return jsonify({"msg": "Não pode alterar seu próprio nível para não-admin."}), 403
         user.role = data['role']

    # Atualizar Status
    if 'is_active' in data and isinstance(data['is_active'], bool):
         if user.email == get_jwt_identity(): return jsonify({"msg": "Não pode alterar seu próprio status aqui. Use a rota /status."}), 403
         user.is_active = data['is_active']

    # Atualizar Plano
    if 'plan_status' in data:
        user.plan_status = data['plan_status']

    # Atualizar Senha
    if 'new_password' in data and data['new_password']:
        new_pass = data['new_password']
        if len(new_pass) < 6: return jsonify({"msg": "Nova senha precisa ter pelo menos 6 caracteres"}), 400
        user.password_hash = generate_password_hash(new_pass)

    # Atualizar Contagem de Páginas (com verificação de mudança)
    if 'page_count' in data:
        try:
            count = int(data['page_count'])
            if count < 0: raise ValueError("Contagem não pode ser negativa")
            if count != old_page_count: # Verifica se realmente mudou
                # O reporte é feito DEPOIS do commit do DB
                new_page_count = count
                page_count_changed = True
                user.page_count = count # Atualiza o objeto user ANTES do commit
        except (ValueError, TypeError):
            return jsonify({"msg": "Contagem de páginas deve ser um número inteiro não negativo."}), 400

    try:
        db.session.commit() # Salva todas as alterações no DB

        # --- Reporta ao Stripe APÓS salvar no DB ---
        if page_count_changed:
            added_pages = new_page_count - old_page_count
            if added_pages > 0: # Só reporta se páginas foram ADICIONADAS
                 report_manual_usage_change(user, added_pages, new_page_count)
            elif added_pages < 0:
                 print(f"AVISO (Admin Edit): Contagem de páginas reduzida para {user.email}. Não é possível reduzir o uso já reportado ao Stripe neste ciclo.")
        # --- Fim do Reporte ---

        return jsonify({"msg": f"Dados do usuário {user.email} atualizados com sucesso.", "user": {"id": user.id, "email": user.email, "role": user.role, "is_active": user.is_active, "page_count": user.page_count, "plan_status": user.plan_status or 'free'}}), 200
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao atualizar dados do usuário {user_id}: {e}")
        traceback.print_exc()
        return jsonify({"msg": "Erro interno ao salvar alterações nos dados do usuário."}), 500
# --- FIM ROTA ATUALIZADA ---


@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required()
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user: return jsonify({"msg": "Usuário não encontrado"}), 404
    current_admin_email = get_jwt_identity()
    if user.email == current_admin_email: return jsonify({"msg": "Não pode excluir sua própria conta."}), 403
    try:
        db.session.delete(user)
        db.session.commit()
        return jsonify({"msg": f"Usuário {user.email} excluído com sucesso."}), 200
    except Exception as e: # <-- ERRO CORRIGIDO AQUI (EOF)
        db.session.rollback()
        print(f"Erro ao excluir usuário {user_id}: {e}")
        return jsonify({"msg": "Erro interno ao excluir usuário."}), 500

@app.route('/api/admin/users/<int:user_id>/reset-pages', methods=['POST'])
@admin_required()
def reset_user_page_count(user_id):
    user = User.query.get(user_id)
    if not user: return jsonify({"msg": "Usuário não encontrado"}), 404

    old_page_count = user.page_count
    user.page_count = 0
    try:
        db.session.commit()
        print(f"AVISO (Admin Reset): Contagem zerada para {user.email}. Uso Stripe não alterado.")
        return jsonify({"msg": f"Contagem de páginas para {user.email} zerada com sucesso."}), 200
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao zerar contagem do usuário {user_id}: {e}")
        return jsonify({"msg": "Erro interno ao zerar contagem."}), 500


@app.route('/api/admin/users/reset-pages', methods=['POST'])
@admin_required()
def reset_all_non_admin_page_counts():
    try:
        updated_count = User.query.filter(User.role != 'admin').update({User.page_count: 0})
        db.session.commit()
        print(f"AVISO (Admin Reset All): Contagem zerada para {updated_count} usuários. Uso Stripe não alterado.")
        return jsonify({"msg": f"Contagem de páginas zerada para {updated_count} usuários (não-admins)."}), 200
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao zerar contagem geral: {e}")
        return jsonify({"msg": "Erro interno ao zerar contagem geral."}), 500

# --- ROTAS DE PAGAMENTO E ASSINATURA (STRIPE) ---

# --- FUNÇÃO get_or_create_stripe_customer (RESTAURADA) ---
def get_or_create_stripe_customer(user):
    """ Busca ou cria um cliente Stripe e salva o ID no DB. """
    if user.stripe_customer_id:
        try:
            stripe.Customer.retrieve(user.stripe_customer_id)
            return user.stripe_customer_id
        except stripe.InvalidRequestError: # Correção aqui
            print(f"ID Stripe {user.stripe_customer_id} inválido para {user.email}. Criando novo.")
            pass

    existing_customers = stripe.Customer.list(email=user.email, limit=1).data
    if existing_customers:
        stripe_customer_id = existing_customers[0].id
        print(f"Cliente Stripe encontrado por email para {user.email}: {stripe_customer_id}")
    else:
        try:
            customer = stripe.Customer.create(email=user.email, metadata={'app_user_id': user.id})
            stripe_customer_id = customer.id
            print(f"Novo cliente Stripe criado para {user.email}: {stripe_customer_id}")
        except Exception as e:
            print(f"Erro ao criar cliente Stripe para {user.email}: {e}")
            raise

    user.stripe_customer_id = stripe_customer_id
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao salvar stripe_customer_id no DB para {user.email}: {e}")

    return stripe_customer_id
# --- FIM FUNÇÃO ---


# --- ROTA DE CHECKOUT ATUALIZADA ---
@app.route('/api/create-checkout-session', methods=['POST'])
@jwt_required()
def create_checkout_session():
    """ Cria uma sessão de checkout com preço fixo e de uso. """
    try:
        data = request.get_json()
        price_id = data.get('priceId')
        if not price_id or price_id not in PRICE_ID_TO_PLAN_NAME:
             raise BadRequest(f"Price ID fixo inválido: {price_id}")

        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user: return jsonify({"msg": "Usuário não encontrado"}), 404

        stripe_customer_id = get_or_create_stripe_customer(user) # <-- Chama a função restaurada
        if not stripe_customer_id: return jsonify({"msg": "Erro cliente Stripe."}), 500

        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
        success_url = f"{frontend_url}/payment-success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{frontend_url}/planos?canceled=true"

        plan_name = PRICE_ID_TO_PLAN_NAME[price_id]
        extra_price_id = PLAN_NAME_TO_EXTRA_PRICE_ID.get(plan_name)

        line_items = [{'price': price_id, 'quantity': 1}]
        if extra_price_id:
            # Importante: O 'extra_price_id' DEVE ser um preço
            # configurado no Stripe para usar o "Medidor" 'pagina_extra'
            line_items.append({'price': extra_price_id})
            print(f"Adicionando preço extra {extra_price_id} para {plan_name}.")
        else:
            print(f"AVISO: Preço extra não encontrado para {plan_name}.")

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='subscription',
            customer=stripe_customer_id,
            success_url=success_url,
            cancel_url=cancel_url,
            allow_promotion_codes=True,
            metadata={ 'app_user_id': user.id },
            subscription_data={ 'metadata': { 'app_user_id': user.id, 'plan_name': plan_name } }
        )
        return jsonify({'url': checkout_session.url})

    except BadRequest as e: return jsonify({"msg": str(e)}), 400
    except stripe.StripeError as e: # Correção aqui
        print(f"Stripe Error checkout: {e}")
        return jsonify({"msg": f"Erro pagamento: {e.user_message or 'Tente.'}"}), 500
    except Exception as e:
        print(f"Erro checkout: {e}"); traceback.print_exc()
        return jsonify({"msg": "Erro interno pagamento."}), 500


@app.route('/api/create-portal-session', methods=['POST'])
@jwt_required()
def create_portal_session():
    """ Cria uma sessão do Portal do Cliente Stripe. """
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user: return jsonify({"msg": "Usuário não encontrado"}), 404

        stripe_customer_id = user.stripe_customer_id
        if not stripe_customer_id:
            stripe_customer_id = get_or_create_stripe_customer(user) # <-- Chama a função restaurada
            if not stripe_customer_id: return jsonify({"msg": "Conta cliente não encontrada."}), 404

        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
        return_url = f"{frontend_url}/app"

        portal_session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id, return_url=return_url, configuration='bpc_1SrNUmF0lzUQm2PeHMTC46vC'
        )
        return jsonify({'url': portal_session.url})

    except stripe.StripeError as e: # Correção aqui
        print(f"Stripe Error portal: {e}")
        if isinstance(e, stripe.InvalidRequestError) and "No configuration provided" in str(e):
             print("ERRO: Portal Stripe não configurado no Dashboard.")
             return jsonify({"msg": "Portal não configurado. Contate suporte."}), 500
        return jsonify({"msg": f"Erro portal: {e.user_message or 'Tente.'}"}), 500
    except Exception as e:
        print(f"Erro portal: {e}"); traceback.print_exc()
        return jsonify({"msg": "Erro interno portal."}), 500

def sync_user_billing_cycle(user_email):
    """Versão 13.0.1+ Robusta: Busca a data de renovação sem quebrar se campos forem nulos."""
    user = User.query.filter_by(email=user_email).first()
    if not user or not user.stripe_customer_id:
        return False
        
    try:
        # 1. Busca a assinatura ativa
        subs = stripe.Subscription.list(
            customer=user.stripe_customer_id, 
            status='active', 
            limit=1
        )
        
        if not subs.data:
            print(f"[STRIPE SYNC] Nenhuma assinatura ativa para {user_email}", flush=True)
            return False
            
        sub = subs.data[0]
        
        # 2. SEMPRE use .get() para evitar o erro de atributo que vimos no log
        timestamp = sub.get('current_period_end')
        
        # 3. Se não tiver na sub, busca na fatura (Plano B)
        if not timestamp:
            invoice_id = sub.get('latest_invoice')
            if invoice_id:
                print(f"[STRIPE SYNC] Buscando via fatura para {user.email}...", flush=True)
                inv = stripe.Invoice.retrieve(invoice_id)
                timestamp = inv.get('period_end')
        
        # 4. Se ainda não tiver, usa a âncora de faturamento (Plano C)
        if not timestamp:
            timestamp = sub.get('billing_cycle_anchor')

        if timestamp:
            # Converte e salva
            user.next_reset_date = datetime.fromtimestamp(timestamp).date()
            db.session.commit()
            print(f"[STRIPE SYNC] SUCESSO: {user.email} atualizado para {user.next_reset_date}", flush=True)
            return True
        
        print(f"[STRIPE SYNC] Falha: Nenhuma data encontrada para {user.email}", flush=True)
        return False
        
    except Exception as e:
        print(f"[STRIPE ERROR] Erro na sync de {user_email}: {str(e)}", flush=True)
        db.session.rollback()
        return False

# --- ROTA DE WEBHOOKS DO STRIPE ---
@app.route('/api/stripe-webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    endpoint_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    if not endpoint_secret: print("ERRO CRÍTICO WEBHOOK: SECRET NÃO CONFIGURADO!"); return "Webhook secret não configurado", 500
    event = None
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError as e: print(f"Webhook error payload: {e}"); return "Invalid payload", 400
    except stripe.SignatureVerificationError as e: print(f"Webhook error signature: {e}"); return "Invalid signature", 400 # Correção aqui
    except Exception as e: print(f"Webhook error construction: {e}"); return "Webhook construction error", 500
    try:
        with app.app_context():
            event_type = event['type']
            event_data = event['data']['object']
            print(f"Webhook recebido: {event_type}")
            if event_type == 'checkout.session.completed': handle_checkout_session_completed(event_data)
            elif event_type == 'invoice.payment_succeeded': handle_invoice_payment_succeeded(event_data)
            elif event_type == 'invoice.payment_failed': handle_invoice_payment_failed(event_data)
            elif event_type == 'customer.subscription.updated': handle_customer_subscription_updated(event_data)
            elif event_type == 'customer.subscription.deleted': handle_customer_subscription_deleted(event_data)
            else: print(f"Evento webhook não manipulado: {event_type}")
    except Exception as e: print(f"Erro CRÍTICO processando webhook {event['type']}: {e}"); traceback.print_exc()
    return jsonify(success=True)

# --- Funções Auxiliares Webhook ---

def find_user_by_stripe_customer_id(stripe_customer_id):
    if not stripe_customer_id: print("Erro Webhook Aux: ID Stripe nulo."); return None
    user = User.query.filter_by(stripe_customer_id=stripe_customer_id).first()
    if not user: print(f"Erro Webhook Aux: Usuário não encontrado para Stripe Customer {stripe_customer_id}")
    return user

def update_user_plan_from_subscription(user, subscription):
    status = subscription.get('status')
    price_id = None
    if subscription.get('items') and subscription['items'].get('data'):
         for item in subscription['items']['data']:
             # Encontra o preço que NÃO é medido (o plano base)
             if item.get('price') and item.get('price').get('recurring', {}).get('usage_type') != 'metered':
                 price_id = item['price']['id']; break
         # Se não achar, pega o primeiro (fallback)
         if not price_id and subscription['items']['data']:
             price_id = subscription['items']['data'][0]['price']['id']

    plan_name = PRICE_ID_TO_PLAN_NAME.get(price_id, 'unknown_plan')

    # Lógica para o caso de o preço de uso medido ser o único item
    if plan_name == 'unknown_plan' and price_id:
        print(f"Webhook Aux: Plano base não encontrado, verificando preço medido {price_id}...")
        # Tenta mapear o plano pelo ID de preço EXTRA
        for plan, extra_id in PLAN_NAME_TO_EXTRA_PRICE_ID.items():
            if extra_id == price_id:
                plan_name = plan
                print(f"Webhook Aux: Plano '{plan_name}' inferido pelo preço extra.")
                break

    new_plan_status = user.plan_status
    if status in ['active', 'trialing']:
        new_plan_status = plan_name
    elif status in ['past_due', 'unpaid', 'incomplete']:
        new_plan_status = 'past_due'
    elif status in ['canceled', 'incomplete_expired']:
        new_plan_status = 'free'
    else:
        print(f"Webhook Aux: Status não mapeado '{status}' para {user.email}");
        return

    if new_plan_status != user.plan_status:
        print(f"Webhook Aux: Atualizando plano {user.email}: '{user.plan_status}' -> '{new_plan_status}' (Stripe: {status})")
        user.plan_status = new_plan_status
    try:
        db.session.commit() # Sempre commita (pode ter zerado page_count)
        print(f"Webhook Aux: Commit OK para {user.email} (Plano: '{user.plan_status}', Stripe: {status}).")
    except Exception as e: print(f"Erro Webhook Aux commit para {user.email}: {e}"); db.session.rollback()

def handle_checkout_session_completed(session):
    app_user_id = session.get('metadata', {}).get('app_user_id')
    stripe_customer_id = session.get('customer')
    subscription_id = session.get('subscription')
    user = None
    if app_user_id: user = User.query.get(app_user_id)
    if not user: print(f"ERRO checkout.comp: User ID {app_user_id} não encontrado"); user = find_user_by_stripe_customer_id(stripe_customer_id)
    if not user: print(f"ERRO checkout.comp: Customer ID {stripe_customer_id} também não encontrado"); return
    print(f"Webhook: Checkout OK - User: {user.email}")
    if stripe_customer_id and not user.stripe_customer_id:
        user.stripe_customer_id = stripe_customer_id; print(f"Webhook: Associando Customer {stripe_customer_id} a {user.email}")
        try: db.session.commit()
        except Exception as e: db.session.rollback(); print(f"Erro ao salvar customer_id: {e}")
    if subscription_id:
        try: subscription = stripe.Subscription.retrieve(subscription_id); update_user_plan_from_subscription(user, subscription); sync_user_billing_cycle(user.email)
        except stripe.StripeError as e: print(f"Erro ao buscar sub {subscription_id}: {e}") # Correção aqui
    else: print(f"AVISO checkout.comp: Sem subscription_id.")

# --- FUNÇÃO ATUALIZADA ---

def handle_invoice_payment_succeeded(invoice):
    stripe_customer_id = invoice.get('customer')
    subscription_id = invoice.get('subscription')
    billing_reason = invoice.get('billing_reason')
    user = find_user_by_stripe_customer_id(stripe_customer_id)
    if not user: return
    
    print(f"Webhook: Pagamento OK - User: {user.email}, Razão: {billing_reason}")
    
    if subscription_id and billing_reason == 'subscription_cycle':
        try:
            print(f"Webhook: Zerando contagem para {user.email} (era {user.page_count}).")
            user.page_count = 0
            # --- ADIÇÃO DO RESET INDIVIDUAL ---
            sync_user_billing_cycle(user.email)
            # ----------------------------------
            subscription = stripe.Subscription.retrieve(subscription_id)
            update_user_plan_from_subscription(user, subscription)
        except stripe.StripeError as e:
            print(f"Erro Stripe zerando contagem {subscription_id}: {e}")
            db.session.rollback()
        except Exception as e:
            print(f"Erro zerando contagem {user.email}: {e}")
            traceback.print_exc()
            db.session.rollback()
            
    elif subscription_id and billing_reason in ['subscription_create', 'subscription_update']:
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            update_user_plan_from_subscription(user, subscription)
            # --- GARANTE A DATA NO NOVO PLANO ---
            sync_user_billing_cycle(user.email)
            # ------------------------------------
        except stripe.StripeError as e:
            print(f"Erro Stripe buscando sub (criação) {subscription_id}: {e}")
        except Exception as e:
            print(f"Erro inesperado na criação/update sub {user.email}: {e}")

def handle_invoice_payment_failed(invoice):
    stripe_customer_id = invoice.get('customer'); subscription_id = invoice.get('subscription')
    user = find_user_by_stripe_customer_id(stripe_customer_id);
    if not user: return
    print(f"Webhook: Pagamento FALHOU - User: {user.email}, Razão: {invoice.get('billing_reason')}")
    if subscription_id:
         try: subscription = stripe.Subscription.retrieve(subscription_id); update_user_plan_from_subscription(user, subscription)
         except stripe.StripeError as e: print(f"Erro Stripe buscando sub (falha) {subscription_id}: {e}") # Correção aqui

def handle_customer_subscription_updated(subscription):
    stripe_customer_id = subscription.get('customer'); user = find_user_by_stripe_customer_id(stripe_customer_id)
    if not user: return
    print(f"Webhook: Assinatura Atualizada - User: {user.email}, Stripe Status: {subscription.get('status')}")
    update_user_plan_from_subscription(user, subscription)

def handle_customer_subscription_deleted(subscription):
    stripe_customer_id = subscription.get('customer'); user = find_user_by_stripe_customer_id(stripe_customer_id)
    if not user: return
    print(f"Webhook: Assinatura EXCLUÍDA - User: {user.email}. Revertendo para 'free'.")
    if user.plan_status != 'free': user.plan_status = 'free'
    try: db.session.commit(); print(f"Webhook: Plano de {user.email} salvo como 'free'.")
    except Exception as e: print(f"Erro ao salvar status 'free' {user.email}: {e}"); db.session.rollback()

# --- FIM DO ARQUIVO auth_service.py ---
