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
import ssl
import secrets
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import timedelta, timezone
# Carrega variáveis de ambiente
load_dotenv()

app = Flask(__name__)

# --- Configurações ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 280,
}
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

# Ranking de planos para distinguir upgrade de downgrade
PLAN_RANK = {'basic': 1, 'standard': 2, 'premium': 3}


# --- Modelos do Banco de Dados ---
class User(db.Model):
    __tablename__ = 'user'

    # --- Ciclo de vida de e-mails ---
    created_at       = db.Column(db.DateTime, nullable=True,
                                 server_default=db.func.now())
    last_activity_at = db.Column(db.DateTime, nullable=True)
    last_renewal_at  = db.Column(db.DateTime, nullable=True)
    email_opt_out    = db.Column(db.Boolean, nullable=False,
                                 default=False, server_default='false')
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=True)
    role = db.Column(db.String(50), nullable=False, default='user')
    is_active = db.Column(db.Boolean, default=True)
    page_count = db.Column(db.Integer, default=0)
    plan_status = db.Column(db.String(50), nullable=False, default='free')
    stripe_customer_id = db.Column(db.String(120), nullable=True, unique=True)
    next_reset_date = db.Column(db.Date, nullable=True)
    email_verified = db.Column(db.Boolean, default=False, nullable=False, server_default='true')
    email_verification_token = db.Column(db.String(128), nullable=True)
    email_verification_sent_at = db.Column(db.DateTime, nullable=True)
# ── Sistema de indicações ────────────────────────────────────────
    referral_code = db.Column(db.String(20), nullable=True, unique=True)
    referred_by_code = db.Column(db.String(20), nullable=True)
    discount_credits = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    extras_reported = db.Column(db.Integer, nullable=False, default=0, server_default='0')
# --- Funções Auxiliares JWT e Decorators ---

# ── Reset de senha ──────────────────────────────────────────────
    password_reset_token   = db.Column(db.String(128), nullable=True, index=True)
    password_reset_sent_at = db.Column(db.DateTime(timezone=True), nullable=True)

# ── Empresa (multi-tenancy) ─────────────────────────────────────
    organization_id = db.Column(db.Integer,
                                db.ForeignKey('organization.id', ondelete='SET NULL'),
                                nullable=True, index=True)
    org_role        = db.Column(db.String(20), nullable=True)   # 'admin' | 'member' | None
    can_process     = db.Column(db.Boolean, nullable=False, default=True)


    # Perfil do usuario (cadastro)
    first_name   = db.Column(db.String(80),  nullable=True)
    last_name    = db.Column(db.String(80),  nullable=True)
    phone        = db.Column(db.String(30),  nullable=True)
    company_name = db.Column(db.String(150), nullable=True)
# ═══════════════════════════════════════════════════════════════════════════
# Classe Organization (multi-tenancy / empresas)
# ═══════════════════════════════════════════════════════════════════════════
class EmailEvent(db.Model):
    """Historico de e-mails do ciclo de vida.

    Fonte unica para tres coisas: idempotencia (nunca reenviar o mesmo
    e-mail), decisao de qual e-mail vem a seguir na regua, e a coluna
    "ultimo e-mail enviado" do painel admin.
    """
    __tablename__ = 'email_event'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer,
                           db.ForeignKey('user.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    email_type = db.Column(db.String(50), nullable=False)
    status     = db.Column(db.String(20), nullable=False,
                           default='sent', server_default='sent')
    sent_at    = db.Column(db.DateTime, nullable=False,
                           default=db.func.now(), server_default=db.func.now())
    meta       = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'email_type': self.email_type,
            'status': self.status,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'meta': self.meta,
        }


class Organization(db.Model):
    __tablename__ = 'organization'

    id                           = db.Column(db.Integer, primary_key=True)
    name                         = db.Column(db.String(120), nullable=False)
    legal_name                   = db.Column(db.String(180), nullable=True)
    cnpj                         = db.Column(db.String(18), nullable=True, unique=True)
    billing_email                = db.Column(db.String(120), nullable=False)
    is_active                    = db.Column(db.Boolean, nullable=False, default=True)

    # Stripe
    stripe_customer_id           = db.Column(db.String(120), nullable=True, unique=True)
    stripe_subscription_id       = db.Column(db.String(120), nullable=True)
    stripe_price_id              = db.Column(db.String(120), nullable=True)

    # Plano e cobrança
    # plan_status: 'awaiting_setup' | 'active' | 'past_due' | 'suspended' | 'inactive'
    plan_status                  = db.Column(db.String(50), nullable=False,
                                             default='awaiting_setup')
    price_per_page_cents         = db.Column(db.Integer, nullable=False, default=62)
    pending_price_per_page_cents = db.Column(db.Integer, nullable=True)
    page_count                   = db.Column(db.Integer, nullable=False, default=0)
    next_reset_date              = db.Column(db.Date, nullable=True)

    # Auditoria
    created_at                   = db.Column(db.DateTime, nullable=False,
                                             default=datetime.utcnow)
    updated_at                   = db.Column(db.DateTime, nullable=False,
                                             default=datetime.utcnow,
                                             onupdate=datetime.utcnow)
    created_by_admin_id          = db.Column(db.Integer,
                                             db.ForeignKey('user.id', ondelete='SET NULL'),
                                             nullable=True)

    # Relacionamento reverso: org.members retorna query de usuários
    members = db.relationship(
        'User',
        backref='organization',
        foreign_keys='User.organization_id',
        lazy='dynamic'
    )

    def __repr__(self):
        return f'<Organization {self.id} {self.name}>'

    def to_dict(self):
        """Serializacao basica usada por endpoints."""
        return {
            'id': self.id,
            'name': self.name,
            'legal_name': self.legal_name,
            'cnpj': self.cnpj,
            'billing_email': self.billing_email,
            'is_active': self.is_active,
            'plan_status': self.plan_status,
            'price_per_page_cents': self.price_per_page_cents,
            'pending_price_per_page_cents': self.pending_price_per_page_cents,
            'page_count': self.page_count,
            'next_reset_date': self.next_reset_date.isoformat() if self.next_reset_date else None,
            'stripe_customer_id': self.stripe_customer_id,
            'stripe_subscription_id': self.stripe_subscription_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

# ── Módulos de indicação e promoções ────────────────────────────────
from referral_service import (
    init_referral_routes,
    ensure_user_has_referral_code,
    process_referral_on_signup,
    on_subscription_created,
    on_invoice_paid_consume_credits,
)
from promotions_service import init_promotions_routes
from announcements_service import init_announcements_routes
from maintenance_service import init_maintenance_routes
from organization_service import init_organization_routes

Referral = init_referral_routes(app, db, User)
Promotion, PromotionMetric = init_promotions_routes(app, db, User)

# ── Painel de e-mails do ciclo de vida ────────────────────────────────
# Envolvido em try/except de proposito: se algo falhar aqui, a aplicacao
# continua subindo normalmente e o erro fica visivel no log.
try:
    from email_admin_api import register_email_admin_routes
    register_email_admin_routes(app)
except Exception as _e:
    print(f"[EMAIL-ADMIN] NAO carregado: {_e}")
Announcement, AnnouncementAck = init_announcements_routes(app, db, User)
MaintenanceWindow = init_maintenance_routes(app, db, User, Announcement=Announcement)

@jwt.additional_claims_loader
def add_claims_to_access_token(identity):
    user = User.query.filter_by(email=identity).first()
    if user:
        return {
            'role':            user.role,
            'is_active':       user.is_active,
            'plan_status':     user.plan_status or 'free',
            'user_id':         user.id,
            # ── Multi-tenancy ────────────────────────────────────────
            'organization_id': user.organization_id,
            'org_role':        user.org_role,
            'can_process':     user.can_process if user.can_process is not None else True,
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


def org_admin_required():
    """
    Permite acesso se o usuario for:
      - admin do sistema (claims['role'] == 'admin'), OU
      - admin de uma empresa (claims['org_role'] == 'admin' e tem org_id).
    """
    def wrapper(fn):
        @wraps(fn)
        @jwt_required()
        def decorator(*args, **kwargs):
            claims = get_jwt()
            if claims.get('role') == 'admin':
                return fn(*args, **kwargs)
            if claims.get('org_role') == 'admin' and claims.get('organization_id'):
                return fn(*args, **kwargs)
            return jsonify(msg="Acesso restrito a administradores."), 403
        return decorator
    return wrapper


def org_member_required():
    """
    Permite acesso se o usuario pertence a alguma empresa (admin ou membro).
    """
    def wrapper(fn):
        @wraps(fn)
        @jwt_required()
        def decorator(*args, **kwargs):
            claims = get_jwt()
            if not claims.get('organization_id'):
                return jsonify(msg="Esta rota e exclusiva de usuarios de empresa."), 403
            return fn(*args, **kwargs)
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
                if not getattr(user, 'email_verified', True):
                    return jsonify({
                        "msg":        "Confirme seu email antes de fazer login.",
                        "error_code": "EMAIL_NOT_VERIFIED",
                        "email":      email,
                    }), 403
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
    ref_code = request.json.get('ref_code', None)
    if not email or not password:
        return jsonify({"msg": "Email e senha são obrigatórios"}), 400
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
         return jsonify({"msg": "Formato de e-mail inválido"}), 400
    if len(password) < 6: return jsonify({"msg": "Senha precisa ter pelo menos 6 caracteres"}), 400
    if not re.search(r"\d", password): return jsonify({"msg": "Senha precisa ter pelo menos 1 número"}), 400
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password): return jsonify({"msg": "Senha precisa ter pelo menos 1 caractere especial"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "Email já cadastrado"}), 409

    token    = secrets.token_urlsafe(32)
    new_user = User(
        email                      = email,
        password_hash              = generate_password_hash(password),
        is_active                  = False,
        role                       = 'user',
        page_count                 = 0,
        plan_status                = 'free',
        email_verified             = False,
        email_verification_token   = token,
        email_verification_sent_at = datetime.now(timezone.utc),
    )
    new_user.first_name   = (request.json.get('first_name')   or '').strip() or None
    new_user.last_name    = (request.json.get('last_name')    or '').strip() or None
    new_user.phone        = (request.json.get('phone')        or '').strip() or None
    new_user.company_name = (request.json.get('company_name')  or '').strip() or None
    db.session.add(new_user)
    try:
        db.session.commit()
        ensure_user_has_referral_code(new_user)
        if ref_code:
            process_referral_on_signup(new_user, ref_code)

        sent = send_verification_email(email, token)
        return jsonify({
            "msg":        "Conta criada! Verifique seu email para ativar.",
            "email_sent": sent,
        }), 201
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

    # Garante que o usuário tenha um código de indicação (gera se não tiver)
    ensure_user_has_referral_code(user)

    claims = get_jwt()
    return jsonify(
    id=user.id,
    email=user.email,
    role=user.role,                      # DB
    is_active=user.is_active,            # DB
    page_count=user.page_count,
    plan_status=user.plan_status or 'free',   # DB — sempre atualizado
    stripe_customer_id=user.stripe_customer_id,
    referral_code=user.referral_code,
    discount_credits=user.discount_credits or 0,
    extras_reported=user.extras_reported or 0,
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
        return jsonify({"users": [{"id": user.id, "email": user.email, "name": ((user.first_name or '') + ' ' + (user.last_name or '')).strip() or None, "first_name": user.first_name, "last_name": user.last_name, "phone": user.phone, "company_name": user.company_name, "role": user.role, "is_active": user.is_active, "page_count": user.page_count, "plan_status": user.plan_status or 'free'} for user in users], "total_pages": pagination.pages, "current_page": page, "total_users": pagination.total}), 200
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
            user.extras_reported = (user.extras_reported or 0) + pages_to_report
            db.session.commit()
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

    # Atualizar dados de perfil (cadastro)
    if 'first_name' in data:
        user.first_name = (data.get('first_name') or '').strip() or None
    if 'last_name' in data:
        user.last_name = (data.get('last_name') or '').strip() or None
    if 'phone' in data:
        user.phone = (data.get('phone') or '').strip() or None
    if 'company_name' in data:
        user.company_name = (data.get('company_name') or '').strip() or None

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
    snapshot_usage(user, 'manual')
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

        # ── Descontos ─────────────────────────────────────────────
        # O Stripe NAO aceita 'discounts' e 'allow_promotion_codes' na
        # mesma sessao: retorna erro e o checkout nem abre. Dai a
        # alternancia. Prioridade: cupom do e-mail > indicacao > nada.
        promo_kwargs = {'allow_promotion_codes': True}
        _codigo = ((data.get('promoCode') or data.get('cupom') or '') or '').strip()
        try:
            from discount_service import (find_promotion_code,
                                          referral_coupon_if_eligible)
            _promo_id = (find_promotion_code(_codigo, stripe_customer_id)
                         if _codigo else None)
            if _promo_id:
                promo_kwargs = {'discounts': [{'promotion_code': _promo_id}]}
                print(f"[CHECKOUT] Cupom {_codigo} aplicado para {user.email}")
            else:
                if _codigo:
                    print(f"[CHECKOUT] Cupom {_codigo} invalido ou expirado "
                          f"para {user.email}.")
                _ref = referral_coupon_if_eligible(user)
                if _ref:
                    promo_kwargs = {'discounts': [{'coupon': _ref}]}
                    print(f"[CHECKOUT] Indicacao: 10% na 1a fatura de {user.email}")
        except Exception as e:
            # Falha aqui nunca pode impedir a assinatura.
            print(f"[CHECKOUT] Erro ao montar desconto: {e}")

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='subscription',
            customer=stripe_customer_id,
            success_url=success_url,
            cancel_url=cancel_url,
            **promo_kwargs,
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

@app.route('/api/change-plan', methods=['POST'])
@jwt_required()
def change_plan():
    """ Troca de plano para assinaturas multi-item (licensed + metered).
        Upgrade  -> imediato, proração na próxima fatura (preserva cupom).
        Downgrade -> agendado para o fim do ciclo (Subscription Schedule). """
    data = request.get_json() or {}
    new_price_id = data.get('priceId')
    when = data.get('when') or 'now'  # 'now' (proração imediata) ou 'period_end' (agendado)
    if when not in ('now', 'period_end'):
        when = 'now'
    if not new_price_id or new_price_id not in PRICE_ID_TO_PLAN_NAME:
        return jsonify({"msg": "Price ID inválido."}), 400

    new_plan  = PRICE_ID_TO_PLAN_NAME[new_price_id]
    new_extra = PLAN_NAME_TO_EXTRA_PRICE_ID.get(new_plan)
    if not new_extra:
        return jsonify({"msg": f"Preço extra do plano {new_plan} não configurado."}), 500

    email = get_jwt_identity()
    user  = User.query.filter_by(email=email).first()
    if not user or not user.stripe_customer_id:
        return jsonify({"msg": "Cliente Stripe não encontrado."}), 404

    try:
        subs = stripe.Subscription.list(
            customer=user.stripe_customer_id, status='active', limit=1
        )
        if not subs.data:
            return jsonify({"msg": "Nenhuma assinatura ativa."}), 404
        sub = subs.data[0]

        lic = next((it for it in sub['items']['data']
                    if (it['price'].get('recurring') or {}).get('usage_type') != 'metered'), None)
        met = next((it for it in sub['items']['data']
                    if (it['price'].get('recurring') or {}).get('usage_type') == 'metered'), None)
        current_plan = PRICE_ID_TO_PLAN_NAME.get(lic['price']['id']) if lic else None

        if current_plan == new_plan:
            return jsonify({"msg": "Você já está neste plano."}), 400

        cur_rank = PLAN_RANK.get(current_plan, 0)
        new_rank = PLAN_RANK.get(new_plan, 0)
        is_upgrade = new_rank > cur_rank

        # UPGRADE imediato (proração) — só se o cliente escolheu "agora".
        # Se for upgrade com when='period_end', cai no fluxo de schedule abaixo.
        if is_upgrade and when == 'now':
            items = [{'id': lic['id'], 'price': new_price_id, 'quantity': 1}]
            if met:
                items.append({'id': met['id'], 'price': new_extra})

            stripe.Subscription.modify(
                sub.id,
                items=items,
                proration_behavior='create_prorations',
                metadata={'app_user_id': user.id, 'plan_name': new_plan},
            )
            if user.plan_status != new_plan:
                user.plan_status = new_plan
                db.session.commit()

            return jsonify({"msg": f"Upgrade para {new_plan} aplicado imediatamente.",
                            "type": "upgrade", "plan": new_plan, "effective": "now"})

        # DOWNGRADE: fim do ciclo
        if sub.get('schedule'):
            return jsonify({"msg": "Já existe uma troca agendada. Aguarde o próximo ciclo."}), 409

        schedule = stripe.SubscriptionSchedule.create(from_subscription=sub.id)
        phase0   = schedule['phases'][0]

        cur_items = []
        for it in sub['items']['data']:
            usage = (it['price'].get('recurring') or {}).get('usage_type')
            cur_items.append({'price': it['price']['id']} if usage == 'metered'
                             else {'price': it['price']['id'], 'quantity': 1})

        new_items = [{'price': new_price_id, 'quantity': 1}, {'price': new_extra}]

        try:
            stripe.SubscriptionSchedule.modify(
                schedule.id,
                end_behavior='release',
                phases=[
                    {'items': cur_items, 'start_date': phase0['start_date'],
                     'end_date': phase0['end_date'], 'proration_behavior': 'none'},
                    {'items': new_items, 'proration_behavior': 'none'},
                ],
            )
        except stripe.StripeError:
            # modify falhou -> libera o schedule recem-criado para nao
            # deixar um schedule orfao travando o usuario em 409.
            try:
                stripe.SubscriptionSchedule.release(schedule.id)
            except stripe.StripeError:
                pass
            raise
        op_type = "upgrade" if is_upgrade else "downgrade"
        return jsonify({"msg": f"Mudança para {new_plan} agendada para o fim do ciclo atual.",
                        "type": op_type, "plan": new_plan, "effective": "period_end"})

    except stripe.StripeError as e:
        print(f"Stripe Error change-plan: {e}"); traceback.print_exc()
        return jsonify({"msg": f"Erro: {getattr(e, 'user_message', None) or 'Tente novamente.'}"}), 500
    except Exception as e:
        print(f"Erro change-plan: {e}"); traceback.print_exc()
        return jsonify({"msg": "Erro interno ao trocar plano."}), 500


@app.route('/api/preview-change-plan', methods=['POST'])
@jwt_required()
def preview_change_plan():
    """Prévia de fatura para upgrade imediato (proração). Não cobra nada."""
    data = request.get_json() or {}
    new_price_id = data.get('priceId')
    if not new_price_id or new_price_id not in PRICE_ID_TO_PLAN_NAME:
        return jsonify({"msg": "Price ID inválido."}), 400

    new_plan  = PRICE_ID_TO_PLAN_NAME[new_price_id]
    new_extra = PLAN_NAME_TO_EXTRA_PRICE_ID.get(new_plan)
    if not new_extra:
        return jsonify({"msg": "Plano não configurado."}), 500

    email = get_jwt_identity()
    user  = User.query.filter_by(email=email).first()
    if not user or not user.stripe_customer_id:
        return jsonify({"msg": "Cliente Stripe não encontrado."}), 404

    try:
        subs = stripe.Subscription.list(
            customer=user.stripe_customer_id, status='active', limit=1
        )
        if not subs.data:
            return jsonify({"msg": "Nenhuma assinatura ativa."}), 404
        sub = subs.data[0]

        lic = next((it for it in sub['items']['data']
                    if (it['price'].get('recurring') or {}).get('usage_type') != 'metered'), None)
        met = next((it for it in sub['items']['data']
                    if (it['price'].get('recurring') or {}).get('usage_type') == 'metered'), None)
        if not lic:
            return jsonify({"msg": "Item licenciado não encontrado."}), 500

        items = [{'id': lic['id'], 'price': new_price_id, 'quantity': 1}]
        if met:
            items.append({'id': met['id'], 'price': new_extra})

        # API nova (stripe>=8) tem create_preview; versões antigas, Invoice.upcoming
        try:
            prev = stripe.Invoice.create_preview(
                customer=user.stripe_customer_id,
                subscription=sub.id,
                subscription_details={
                    "items": items,
                    "proration_behavior": "create_prorations",
                },
            )
        except AttributeError:
            prev = stripe.Invoice.upcoming(
                customer=user.stripe_customer_id,
                subscription=sub.id,
                subscription_items=items,
                subscription_proration_behavior="create_prorations",
            )

        return jsonify({
            "amount_due": prev.get("amount_due", 0),
            "currency":   prev.get("currency", "brl"),
        })
    except stripe.StripeError as e:
        print(f"Stripe Error preview-change-plan: {e}")
        return jsonify({"msg": f"Erro: {getattr(e, 'user_message', None) or 'Tente novamente.'}"}), 500
    except Exception as e:
        import traceback
        print(f"Erro preview-change-plan: {e}"); traceback.print_exc()
        return jsonify({"msg": "Erro interno na prévia."}), 500


@app.route('/api/subscription-status', methods=['GET'])
@jwt_required()
def subscription_status():
    """ Plano atual + troca agendada (downgrade pendente), se houver. """
    email = get_jwt_identity()
    user  = User.query.filter_by(email=email).first()
    if not user or not user.stripe_customer_id:
        return jsonify({"current_plan": (user.plan_status if user else "free"),
                        "scheduled_change": None})
    try:
        subs = stripe.Subscription.list(
            customer=user.stripe_customer_id, status='active', limit=1
        )
        if not subs.data:
            return jsonify({"current_plan": user.plan_status, "scheduled_change": None})
        sub = subs.data[0]

        lic = next((it for it in sub['items']['data']
                    if (it['price'].get('recurring') or {}).get('usage_type') != 'metered'), None)
        current_plan = PRICE_ID_TO_PLAN_NAME.get(lic['price']['id']) if lic else user.plan_status

        scheduled = None
        sched_id = sub.get('schedule')
        if sched_id:
            sched  = stripe.SubscriptionSchedule.retrieve(sched_id)
            phases = sched.get('phases') or []
            if len(phases) >= 2:
                future = phases[1]
                target_plan = None
                for it in future.get('items', []):
                    pid = it['price'] if isinstance(it['price'], str) else it['price'].get('id')
                    if pid in PRICE_ID_TO_PLAN_NAME:
                        target_plan = PRICE_ID_TO_PLAN_NAME[pid]
                        break
                effective_ts = phases[0].get('end_date') or future.get('start_date')
                scheduled = {"plan": target_plan, "effective_date": effective_ts}
        return jsonify({"current_plan": current_plan, "scheduled_change": scheduled})
    except stripe.StripeError as e:
        print(f"Stripe Error subscription-status: {e}")
        return jsonify({"current_plan": user.plan_status, "scheduled_change": None})


@app.route('/api/cancel-scheduled-change', methods=['POST'])
@jwt_required()
def cancel_scheduled_change():
    """ Cancela um downgrade agendado (libera o schedule). Mantém o plano atual. """
    email = get_jwt_identity()
    user  = User.query.filter_by(email=email).first()
    if not user or not user.stripe_customer_id:
        return jsonify({"msg": "Cliente Stripe não encontrado."}), 404
    try:
        subs = stripe.Subscription.list(
            customer=user.stripe_customer_id, status='active', limit=1
        )
        if not subs.data:
            return jsonify({"msg": "Nenhuma assinatura ativa."}), 404
        sched_id = subs.data[0].get('schedule')
        if not sched_id:
            return jsonify({"msg": "Nenhuma troca agendada para cancelar."}), 400
        stripe.SubscriptionSchedule.release(sched_id)
        return jsonify({"msg": "Troca de plano cancelada. Você permanece no plano atual."})
    except stripe.StripeError as e:
        print(f"Stripe Error cancel-scheduled: {e}"); traceback.print_exc()
        return jsonify({"msg": f"Erro: {getattr(e, 'user_message', None) or 'Tente novamente.'}"}), 500
    except Exception as e:
        print(f"Erro cancel-scheduled: {e}"); traceback.print_exc()
        return jsonify({"msg": "Erro interno."}), 500


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
# ── NOVO: route org events to org handlers ─────────────
            try:
                from stripe_org_service import route_org_webhook_if_applicable
                if route_org_webhook_if_applicable(event):
                    print(f"[ORG-WEBHOOK] routed: {event_type}")
                    return jsonify(success=True)
            except Exception as _org_route_err:
                print(f"[ORG-WEBHOOK ERRO] routing falhou: {_org_route_err}")
                traceback.print_exc()
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
        new_plan_status = 'inactive'
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
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            update_user_plan_from_subscription(user, subscription)
            sync_user_billing_cycle(user.email)

            # ── Sistema de indicações: marca conversão ────────────
            try:
                # Boas-vindas + indicacao: o checkout aplicou 20% na 1a
                # fatura; aqui entram os 10% dos meses 2 e 3.
                try:
                    from discount_service import maybe_apply_welcome_remainder
                    maybe_apply_welcome_remainder(user, subscription.id)
                except Exception as e:
                    print(f"[DESCONTO] Erro no complemento de boas-vindas: {e}")

                on_subscription_created(user, subscription)

                # Ciclo de vida: e-mail de obrigado + marca o inicio do ciclo.
                try:
                    from lifecycle_hooks import on_subscription_started
                    on_subscription_started(user)
                except Exception as _e:
                    print(f"[CICLO] Erro no gancho de assinatura: {_e}")
            except Exception as e:
                print(f"[REFERRAL] Erro no hook on_subscription_created: {e}")
                traceback.print_exc()

        except stripe.StripeError as e:
            print(f"Erro ao buscar sub {subscription_id}: {e}")
    else:
        print(f"AVISO checkout.comp: Sem subscription_id.")    


# --- FUNÇÃO ATUALIZADA ---

def _invoice_subscription_id(invoice):
    """ID da assinatura — compativel com schema novo (parent) e antigo (topo)."""
    sid = invoice.get('subscription')
    if sid:
        return sid
    parent = invoice.get('parent') or {}
    return (parent.get('subscription_details') or {}).get('subscription')


def _invoice_period_end_date(invoice):
    """Maior fim de periodo entre as linhas de assinatura. Sinal de 'novo ciclo'.
    Compativel com API 2025-09-30.clover (subscription/price em parent/pricing)."""
    ends = []
    try:
        for line in (invoice.get('lines', {}) or {}).get('data', []):
            parent   = line.get('parent') or {}
            sub_item = parent.get('subscription_item_details') or {}
            is_sub   = bool(sub_item.get('subscription') or line.get('subscription'))
            recurring = (line.get('price', {}) or {}).get('recurring')
            if is_sub or recurring:
                ts = (line.get('period', {}) or {}).get('end')
                if ts:
                    ends.append(ts)
    except Exception:
        pass
    if ends:
        return datetime.fromtimestamp(max(ends)).date()
    ts = invoice.get('period_end')
    if ts:
        return datetime.fromtimestamp(ts).date()
    return None


def handle_invoice_payment_succeeded(invoice):
    stripe_customer_id = invoice.get('customer')
    subscription_id    = _invoice_subscription_id(invoice)
    billing_reason     = invoice.get('billing_reason')
    user = find_user_by_stripe_customer_id(stripe_customer_id)
    if not user:
        return

    print(f"Webhook: Pagamento OK - User: {user.email}, Razão: {billing_reason}")

    if not subscription_id:
        print(f"Webhook: fatura sem subscription para {user.email}; sem reset.")
        return

    try:
        # ── Reset decidido pelo PERÍODO, não pelo billing_reason ──
        # Renovações chegam ora como 'subscription_cycle', ora como
        # 'subscription_update' (proration/cupom/medidor). O sinal confiável de
        # "novo ciclo" é o fim de período da fatura ter avançado além do último
        # reset registrado (next_reset_date). Idempotente em redelivery.
        new_period_end = _invoice_period_end_date(invoice)
        old_reset_date = user.next_reset_date

        is_new_cycle = (
            new_period_end is not None
            and (old_reset_date is None or new_period_end > old_reset_date)
        )

        if is_new_cycle:
            print(f"Webhook: NOVO CICLO {old_reset_date} -> {new_period_end}. "
                  f"Zerando {user.email} (era {user.page_count}).")
            snapshot_usage(user, 'renewal', period_end=old_reset_date)
            _usadas_ciclo_anterior = user.page_count or 0   # antes de zerar
            user.page_count = 0
            user.extras_reported = 0
        else:
            print(f"Webhook: Mesma janela ({old_reset_date}); NÃO zera "
                  f"{user.email} (reason={billing_reason}).")

        # Plano e data de renovação atualizados em qualquer caso.
        subscription = stripe.Subscription.retrieve(subscription_id)
        update_user_plan_from_subscription(user, subscription)   # commita
        sync_user_billing_cycle(user.email)                      # commita + grava next_reset_date

        # Ciclo de vida: e-mail de renovacao (so em ciclo novo).
        if is_new_cycle:
            try:
                from lifecycle_hooks import on_renewal
                on_renewal(user, _usadas_ciclo_anterior)
            except Exception as _e:
                print(f"[CICLO] Erro no gancho de renovacao: {_e}")

        # Indicações: só consome créditos / reaplica cupom em ciclo novo.
        if is_new_cycle and billing_reason in ('subscription_cycle', 'subscription_update'):
            try:
                on_invoice_paid_consume_credits(user, invoice)
            except Exception as e:
                print(f"[REFERRAL] Erro no hook on_invoice_paid_consume_credits: {e}")
                traceback.print_exc()

    except stripe.StripeError as e:
        print(f"Erro Stripe processando fatura paga ({subscription_id}): {e}")
        db.session.rollback()
    except Exception as e:
        print(f"Erro processando fatura paga {user.email}: {e}")
        traceback.print_exc()
        db.session.rollback()

def handle_invoice_payment_failed(invoice):
    stripe_customer_id = invoice.get('customer')
    # Schema 2025-09-30.clover moveu 'subscription' para
    # invoice.parent.subscription_details.subscription. Com o caminho antigo
    # o id vinha None e o plano nunca ia para 'past_due'.
    subscription_id = _invoice_subscription_id(invoice)
    user = find_user_by_stripe_customer_id(stripe_customer_id)
    if not user: return
    print(f"Webhook: Pagamento FALHOU - User: {user.email}, Razão: {invoice.get('billing_reason')}")

    # Ciclo de vida: avisa o cliente para atualizar o cartao.
    try:
        from lifecycle_hooks import on_payment_failed
        _v = invoice.get('amount_due')
        on_payment_failed(user,
                          f"R$ {_v/100:.2f}".replace('.', ',') if _v else None)
    except Exception as _e:
        print(f"[CICLO] Erro no gancho de pagamento falhou: {_e}")
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
    print(f"Webhook: Assinatura EXCLUÍDA - User: {user.email}. Marcando como 'inactive'.")
    if user.plan_status != 'inactive': user.plan_status = 'inactive'
    try:
        db.session.commit()
        print(f"Webhook: Plano de {user.email} salvo como 'inactive'.")

        # Ciclo de vida: avisa que a assinatura terminou e oferece reativacao.
        try:
            from lifecycle_hooks import on_subscription_ended
            on_subscription_ended(user)
        except Exception as _e:
            print(f"[CICLO] Erro no gancho de assinatura encerrada: {_e}")
    except Exception as e:
        print(f"Erro ao salvar status 'inactive' {user.email}: {e}")
        db.session.rollback()
def send_verification_email(user_email: str, token: str) -> bool:
    smtp_host     = os.getenv("SMTP_HOST")
    smtp_port     = int(os.getenv("SMTP_PORT", "587"))
    smtp_user     = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    from_name     = os.getenv("SMTP_FROM_NAME", "Sistema Ponto")
    frontend_url  = os.getenv("FRONTEND_URL", "https://sistemaponto.com")
 
    if not all([smtp_host, smtp_user, smtp_password]):
        print("[EMAIL] ERRO: variáveis SMTP não configuradas no .env")
        return False
 
    verify_url = f"{frontend_url}/verificar-email?token={token}"
 
    html_body = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0d1117;font-family:-apple-system,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0d1117;padding:40px 20px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#161b22;border-radius:12px;border:1px solid #30363d;max-width:560px;width:100%;">
        <tr><td style="background:linear-gradient(135deg,#1a3a5c,#0d2137);padding:32px 40px;text-align:center;">
          <h1 style="margin:0;color:#4a9eff;font-size:22px;font-weight:700;">Sistema Ponto</h1>
          <p style="margin:8px 0 0;color:#8b9dc3;font-size:13px;">Automação de cartões de ponto com IA</p>
        </td></tr>
        <tr><td style="padding:40px;">
          <h2 style="margin:0 0 16px;color:#e6edf3;font-size:20px;">Confirme seu e-mail</h2>
          <p style="margin:0 0 8px;color:#8b949e;font-size:15px;line-height:1.6;">
            Obrigado por se cadastrar! Clique no botão abaixo para ativar sua conta e ganhar
            <strong style="color:#4a9eff;">50 páginas grátis</strong>.
          </p>
          <p style="margin:0 0 32px;color:#6e7681;font-size:13px;">
            Este link expira em <strong style="color:#8b949e;">24 horas</strong>.
          </p>
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td align="center" style="padding:0 0 32px;">
              <a href="{verify_url}"
                 style="display:inline-block;background:linear-gradient(135deg,#1a6bd6,#4a9eff);
                        color:#fff;text-decoration:none;font-weight:700;font-size:15px;
                        padding:14px 40px;border-radius:8px;">
                ✓ &nbsp; Verificar meu e-mail
              </a>
            </td></tr>
          </table>
          <div style="background:#0d1117;border-radius:8px;padding:16px;border:1px solid #30363d;">
            <p style="margin:0 0 8px;color:#6e7681;font-size:12px;">Ou copie este link no navegador:</p>
            <p style="margin:0;color:#4a9eff;font-size:12px;word-break:break-all;">{verify_url}</p>
          </div>
        </td></tr>
        <tr><td style="padding:24px 40px;border-top:1px solid #21262d;text-align:center;">
          <p style="margin:0;color:#6e7681;font-size:12px;">
            Se você não criou uma conta no Sistema Ponto, ignore este email.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
 
    text_body = f"""Confirme seu email no Sistema Ponto.
 
Clique no link abaixo para ativar sua conta e ganhar 50 páginas grátis (expira em 24h):
{verify_url}
 
Se você não criou uma conta, ignore este email.
"""
 
    try:
        msg            = MIMEMultipart("alternative")
        msg["Subject"] = "✓ Confirme seu e-mail — Sistema Ponto"
        msg["From"]    = f"{from_name} <{smtp_user}>"
        msg["To"]      = user_email
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html",  "utf-8"))
        
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, user_email, msg.as_string()) 
 
        print(f"[EMAIL] Verificação enviada para {user_email}")
        return True
    except Exception as e:
        print(f"[EMAIL] ERRO ao enviar para {user_email}: {e}")
        return False
 
 
# --- Rota: verificar token do email ---
 
@app.route('/api/auth/verify-email', methods=['GET'])
def verify_email():
    token = request.args.get('token', '').strip()
    if not token:
        return jsonify({"msg": "Token não fornecido.", "error_code": "NO_TOKEN"}), 400
 
    user = User.query.filter_by(email_verification_token=token).first()
    if not user:
        return jsonify({"msg": "Link inválido ou já utilizado.", "error_code": "INVALID_TOKEN"}), 400
 
    # Checa expiração (24h)
    if user.email_verification_sent_at:
        sent_at = user.email_verification_sent_at
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - sent_at > timedelta(hours=24):
            return jsonify({
                "msg":        "Link expirado. Solicite um novo email de verificação.",
                "error_code": "TOKEN_EXPIRED",
                "email":      user.email,
            }), 400
 
    try:
        user.email_verified             = True
        user.is_active                  = True
        user.email_verification_token   = None
        user.email_verification_sent_at = None
        db.session.commit()
        print(f"[EMAIL] Verificado com sucesso: {user.email}")

        # Ciclo de vida: boas-vindas so aqui, nunca no /api/register.
        # No cadastro a conta ainda esta bloqueada e o usuario acabou de
        # receber o e-mail de verificacao — dois e-mails ao mesmo tempo se
        # contradiriam ("confirme para ganhar" x "voce ja tem").
        try:
            from lifecycle_hooks import on_user_registered
            on_user_registered(user)
        except Exception as _e:
            print(f"[CICLO] Erro no gancho de boas-vindas: {_e}")

        return jsonify({"msg": "Email verificado! Sua conta está ativa.", "success": True}), 200
    except Exception as e:
        db.session.rollback()
        print(f"[EMAIL] Erro ao verificar {user.email}: {e}")
        return jsonify({"msg": "Erro interno ao ativar conta."}), 500
 
 
# --- Rota: reenviar email de verificação ---
 
@app.route('/api/auth/resend-verification', methods=['POST'])
def resend_verification():
    email = request.json.get('email', '').strip().lower()
    if not email:
        return jsonify({"msg": "Email obrigatório."}), 400
 
    user = User.query.filter_by(email=email).first()
 
    # Sempre responde igual (evita enumeração de emails)
    if not user or getattr(user, 'email_verified', True):
        return jsonify({"msg": "Se o email existir e não estiver verificado, você receberá o link em instantes."}), 200
 
    # Rate limit: 1 reenvio a cada 60 segundos
    if user.email_verification_sent_at:
        sent_at = user.email_verification_sent_at
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - sent_at).total_seconds()
        if elapsed < 60:
            wait = int(60 - elapsed)
            return jsonify({"msg": f"Aguarde {wait}s antes de solicitar outro email.", "retry_after": wait}), 429
 
    try:
        new_token                          = secrets.token_urlsafe(32)
        user.email_verification_token      = new_token
        user.email_verification_sent_at    = datetime.now(timezone.utc)
        db.session.commit()
        send_verification_email(email, new_token)
        return jsonify({"msg": "Email de verificação reenviado."}), 200
    except Exception as e:
        db.session.rollback()
        print(f"[EMAIL] Erro ao reenviar para {email}: {e}")
        return jsonify({"msg": "Erro ao reenviar email. Tente novamente."}), 500


# ════════════════════════════════════════════════════════════════════
#                     RESET DE SENHA (Forgot Password)
# ════════════════════════════════════════════════════════════════════

def send_password_reset_email(user_email: str, token: str) -> bool:
    smtp_host     = os.getenv("SMTP_HOST")
    smtp_port     = int(os.getenv("SMTP_PORT", "465"))
    smtp_user     = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    from_name     = os.getenv("SMTP_FROM_NAME", "Sistema Ponto")
    frontend_url  = os.getenv("FRONTEND_URL", "https://sistemaponto.com")

    if not all([smtp_host, smtp_user, smtp_password]):
        print("[EMAIL] ERRO: variáveis SMTP não configuradas no .env")
        return False

    reset_url = f"{frontend_url}/redefinir-senha?token={token}"

    html_body = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0d1117;font-family:-apple-system,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0d1117;padding:40px 20px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#161b22;border-radius:12px;border:1px solid #30363d;max-width:560px;width:100%;">
        <tr><td style="background:linear-gradient(135deg,#1a3a5c,#0d2137);padding:32px 40px;text-align:center;">
          <h1 style="margin:0;color:#4a9eff;font-size:22px;font-weight:700;">Sistema Ponto</h1>
          <p style="margin:8px 0 0;color:#8b9dc3;font-size:13px;">Redefinição de senha</p>
        </td></tr>
        <tr><td style="padding:40px;">
          <h2 style="margin:0 0 16px;color:#e6edf3;font-size:20px;">Solicitação de redefinição de senha</h2>
          <p style="margin:0 0 8px;color:#8b949e;font-size:15px;line-height:1.6;">
            Recebemos uma solicitação para redefinir a senha da sua conta.
            Clique no botão abaixo para criar uma nova senha.
          </p>
          <p style="margin:0 0 32px;color:#6e7681;font-size:13px;">
            Este link expira em <strong style="color:#8b949e;">1 hora</strong> e só pode ser usado uma vez.
          </p>
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td align="center" style="padding:0 0 32px;">
              <a href="{reset_url}"
                 style="display:inline-block;background:linear-gradient(135deg,#1a6bd6,#4a9eff);
                        color:#fff;text-decoration:none;font-weight:700;font-size:15px;
                        padding:14px 40px;border-radius:8px;">
                🔑 &nbsp; Redefinir minha senha
              </a>
            </td></tr>
          </table>
          <div style="background:#0d1117;border-radius:8px;padding:16px;border:1px solid #30363d;">
            <p style="margin:0 0 8px;color:#6e7681;font-size:12px;">Ou copie este link no navegador:</p>
            <p style="margin:0;color:#4a9eff;font-size:12px;word-break:break-all;">{reset_url}</p>
          </div>
          <div style="margin-top:24px;padding:16px;background:#1c1410;border-radius:8px;border:1px solid #5a3a1f;">
            <p style="margin:0;color:#d4924a;font-size:13px;line-height:1.5;">
              ⚠️ <strong>Não foi você?</strong> Ignore este email — sua senha permanecerá a mesma.
              Ninguém pode redefinir sua senha sem acesso à sua caixa de entrada.
            </p>
          </div>
        </td></tr>
        <tr><td style="padding:24px 40px;border-top:1px solid #21262d;text-align:center;">
          <p style="margin:0;color:#6e7681;font-size:12px;">
            Sistema Ponto · sistemaponto.com<br>
            Email automático, não responda.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    text_body = f"""Redefinição de senha — Sistema Ponto

Recebemos uma solicitação para redefinir sua senha.
Clique no link abaixo (expira em 1 hora):

{reset_url}

Não foi você? Ignore este email — sua senha permanecerá a mesma.
"""

    try:
        msg            = MIMEMultipart("alternative")
        msg["Subject"] = "🔑 Redefinir senha — Sistema Ponto"
        msg["From"]    = f"{from_name} <{smtp_user}>"
        msg["To"]      = user_email
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html",  "utf-8"))

        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, user_email, msg.as_string())

        print(f"[EMAIL] Reset de senha enviado para {user_email}")
        return True
    except Exception as e:
        print(f"[EMAIL] ERRO ao enviar reset para {user_email}: {e}")
        return False


def send_password_changed_notification(user_email: str, ip: str = "desconhecido") -> bool:
    smtp_host     = os.getenv("SMTP_HOST")
    smtp_port     = int(os.getenv("SMTP_PORT", "465"))
    smtp_user     = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    from_name     = os.getenv("SMTP_FROM_NAME", "Sistema Ponto")
    frontend_url  = os.getenv("FRONTEND_URL", "https://sistemaponto.com")

    if not all([smtp_host, smtp_user, smtp_password]):
        return False

    when = datetime.now(timezone.utc).strftime("%d/%m/%Y às %H:%M UTC")

    html_body = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0d1117;font-family:-apple-system,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0d1117;padding:40px 20px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#161b22;border-radius:12px;border:1px solid #30363d;max-width:560px;width:100%;">
        <tr><td style="background:linear-gradient(135deg,#1a3a5c,#0d2137);padding:32px 40px;text-align:center;">
          <h1 style="margin:0;color:#4a9eff;font-size:22px;font-weight:700;">Sistema Ponto</h1>
          <p style="margin:8px 0 0;color:#8b9dc3;font-size:13px;">Confirmação de segurança</p>
        </td></tr>
        <tr><td style="padding:40px;">
          <h2 style="margin:0 0 16px;color:#e6edf3;font-size:20px;">✓ Sua senha foi alterada</h2>
          <p style="margin:0 0 16px;color:#8b949e;font-size:15px;line-height:1.6;">
            A senha da sua conta foi alterada em <strong style="color:#e6edf3;">{when}</strong>
            (IP: <code style="color:#8b9dc3;">{ip}</code>).
          </p>
          <div style="margin-top:24px;padding:16px;background:#1c1410;border-radius:8px;border:1px solid #5a3a1f;">
            <p style="margin:0 0 8px;color:#d4924a;font-size:14px;font-weight:600;">⚠️ Não foi você?</p>
            <p style="margin:0;color:#d4924a;font-size:13px;line-height:1.5;">
              Sua conta pode ter sido comprometida. Acesse imediatamente
              <a href="{frontend_url}/esqueci-senha" style="color:#4a9eff;">{frontend_url}/esqueci-senha</a>
              para criar uma nova senha e entre em contato com o suporte:
              <strong>contato@sistemaponto.com</strong>.
            </p>
          </div>
        </td></tr>
        <tr><td style="padding:24px 40px;border-top:1px solid #21262d;text-align:center;">
          <p style="margin:0;color:#6e7681;font-size:12px;">Sistema Ponto · sistemaponto.com</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    text_body = f"""Sua senha foi alterada em {when} (IP: {ip}).

Não foi você? Acesse {frontend_url}/esqueci-senha imediatamente
e contate o suporte em contato@sistemaponto.com.
"""

    try:
        msg            = MIMEMultipart("alternative")
        msg["Subject"] = "✓ Sua senha foi alterada — Sistema Ponto"
        msg["From"]    = f"{from_name} <{smtp_user}>"
        msg["To"]      = user_email
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html",  "utf-8"))

        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, user_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[EMAIL] ERRO ao enviar notificação de senha alterada para {user_email}: {e}")
        return False


@app.route('/api/auth/forgot-password', methods=['POST'])
def forgot_password():
    email = (request.json.get('email') or '').strip().lower()
    if not email:
        return jsonify({"msg": "Email obrigatório."}), 400

    generic_response = (jsonify({
        "msg": "Se este email estiver cadastrado, você receberá as instruções de redefinição em instantes."
    }), 200)

    user = User.query.filter_by(email=email).first()

    if not user:
        print(f"[RESET] Tentativa para email inexistente: {email}")
        return generic_response

    if not user.password_hash:
        print(f"[RESET] Tentativa em conta Google-only: {email}")
        return generic_response

    if user.password_reset_sent_at:
        sent_at = user.password_reset_sent_at
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - sent_at).total_seconds()
        if elapsed < 60:
            print(f"[RESET] Rate limit ({int(elapsed)}s) para {email}")
            return generic_response

    try:
        token = secrets.token_urlsafe(32)
        user.password_reset_token   = token
        user.password_reset_sent_at = datetime.now(timezone.utc)
        db.session.commit()
        send_password_reset_email(email, token)
    except Exception as e:
        db.session.rollback()
        print(f"[RESET] Erro ao gerar token para {email}: {e}")

    return generic_response


@app.route('/api/auth/verify-reset-token', methods=['GET'])
def verify_reset_token():
    token = (request.args.get('token') or '').strip()
    if not token:
        return jsonify({"valid": False, "error_code": "NO_TOKEN"}), 400

    user = User.query.filter_by(password_reset_token=token).first()
    if not user:
        return jsonify({"valid": False, "error_code": "INVALID_TOKEN"}), 400

    if user.password_reset_sent_at:
        sent_at = user.password_reset_sent_at
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - sent_at > timedelta(hours=1):
            return jsonify({"valid": False, "error_code": "TOKEN_EXPIRED"}), 400

    return jsonify({"valid": True}), 200


@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    token        = (request.json.get('token') or '').strip()
    new_password = request.json.get('new_password') or ''

    if not token:
        return jsonify({"msg": "Token não fornecido."}), 400

    if len(new_password) < 6:
        return jsonify({"msg": "Senha precisa ter pelo menos 6 caracteres."}), 400
    if not re.search(r"\d", new_password):
        return jsonify({"msg": "Senha precisa ter pelo menos 1 número."}), 400
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", new_password):
        return jsonify({"msg": "Senha precisa ter pelo menos 1 caractere especial."}), 400

    user = User.query.filter_by(password_reset_token=token).first()
    if not user:
        return jsonify({"msg": "Link inválido ou já utilizado.", "error_code": "INVALID_TOKEN"}), 400

    if user.password_reset_sent_at:
        sent_at = user.password_reset_sent_at
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - sent_at > timedelta(hours=1):
            return jsonify({
                "msg": "Link expirado. Solicite um novo email de redefinição.",
                "error_code": "TOKEN_EXPIRED",
            }), 400

    if user.password_hash and check_password_hash(user.password_hash, new_password):
        return jsonify({"msg": "A nova senha deve ser diferente da senha atual."}), 400

    try:
        user.password_hash          = generate_password_hash(new_password)
        user.password_reset_token   = None
        user.password_reset_sent_at = None
        if not user.email_verified:
            user.email_verified = True
            user.is_active      = True
        db.session.commit()
        print(f"[RESET] Senha redefinida com sucesso: {user.email}")

        ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'desconhecido').split(',')[0].strip()
        try:
            send_password_changed_notification(user.email, ip)
        except Exception as e:
            print(f"[RESET] Aviso: falha ao enviar email de notificação: {e}")

        return jsonify({"msg": "Senha redefinida com sucesso! Faça login.", "success": True}), 200
    except Exception as e:
        db.session.rollback()
        print(f"[RESET] Erro ao salvar nova senha para {user.email}: {e}")
        return jsonify({"msg": "Erro interno ao redefinir senha."}), 500
# --- FIM DO ARQUIVO auth_service.py ---

# ─── Multi-tenancy: registrar APOS admin_required estar definido ───
init_organization_routes(app, db, User, Organization, admin_required, org_admin_required)


# ===================================================================
# [usage_snapshot patch] Historico de uso mensal por usuario
# ===================================================================
class UsageSnapshot(db.Model):
    __tablename__ = 'usage_snapshot'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    reference_month = db.Column(db.Date, nullable=False)
    plan_status = db.Column(db.String(50), nullable=False)
    pages_used = db.Column(db.Integer, nullable=False, default=0)
    pages_included = db.Column(db.Integer, nullable=False, default=0)
    extras = db.Column(db.Integer, nullable=False, default=0)
    period_end = db.Column(db.Date, nullable=True)
    snapshot_reason = db.Column(db.String(20), nullable=False, default='renewal')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'reference_month', name='uq_usage_user_month'),)


def snapshot_usage(user, reason='renewal', period_end=None):
    # Grava 1 linha de historico ANTES de zerar page_count.
    # Idempotente por (user, mes). Nunca levanta excecao (nao pode quebrar o reset).
    try:
        ref = period_end or user.next_reset_date or datetime.utcnow().date()
        ref_month = datetime(ref.year, ref.month, 1).date()
        exists = UsageSnapshot.query.filter_by(user_id=user.id, reference_month=ref_month).first()
        if exists:
            return
        plan = user.plan_status or 'free'
        included = PLAN_LIMITS.get(plan, 0)
        used = user.page_count or 0
        extras = max(0, used - included)
        snap = UsageSnapshot(
            user_id=user.id, reference_month=ref_month, plan_status=plan,
            pages_used=used, pages_included=included, extras=extras,
            period_end=ref, snapshot_reason=reason,
        )
        nested = db.session.begin_nested()
        try:
            db.session.add(snap)
            db.session.flush()
            nested.commit()
            print(f"[usage_snapshot] {user.email}: {plan} {used}pg mes {ref_month} ({reason})")
        except Exception as e_inner:
            nested.rollback()
            print(f"[usage_snapshot] rollback {user.email}: {e_inner}")
    except Exception as e:
        print(f"[usage_snapshot] erro {getattr(user, 'email', '?')}: {e}")


_MESES_PT = ['', 'jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
_PLAN_LABEL_HIST = {'free': 'Free Trial', 'basic': 'Basico', 'standard': 'Padrao', 'premium': 'Premium', 'past_due': 'Pend.', 'inactive': 'Inativo', 'awaiting_setup': 'Config.'}


@app.route('/api/admin/users/<int:user_id>/usage-history', methods=['GET'])
@admin_required()
def get_user_usage_history(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "Usuario nao encontrado"}), 404

    rows = (UsageSnapshot.query
            .filter_by(user_id=user.id)
            .order_by(UsageSnapshot.reference_month.desc())
            .all())

    def _fmt(d):
        return f"{_MESES_PT[d.month]}/{d.year}"

    history = []
    plan_now = user.plan_status or 'free'
    incl_now = PLAN_LIMITS.get(plan_now, 0)
    used_now = user.page_count or 0
    ref_now = user.next_reset_date or datetime.utcnow().date()
    ref_now_month = datetime(ref_now.year, ref_now.month, 1).date()
    already_closed = any(r.reference_month == ref_now_month for r in rows)
    if not already_closed:
        history.append({
            "month": ref_now_month.isoformat(),
            "label": _fmt(ref_now_month),
            "plan_status": plan_now,
            "plan_label": _PLAN_LABEL_HIST.get(plan_now, plan_now),
            "pages_used": used_now,
            "pages_included": incl_now,
            "extras": max(0, used_now - incl_now),
            "in_progress": True,
        })

    for r in rows:
        history.append({
            "month": r.reference_month.isoformat(),
            "label": _fmt(r.reference_month),
            "plan_status": r.plan_status,
            "plan_label": _PLAN_LABEL_HIST.get(r.plan_status, r.plan_status),
            "pages_used": r.pages_used,
            "pages_included": r.pages_included,
            "extras": r.extras,
            "in_progress": False,
        })

    return jsonify({"email": user.email, "history": history}), 200
# [usage_snapshot patch] fim
