# /opt/pontua/AutoPonto/backend_api/auth_service.py
import os
from flask import Flask, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, JWTManager, get_jwt_identity, get_jwt
from requests_oauthlib import OAuth2Session
from dotenv import load_dotenv
import functools

load_dotenv() # Carrega variáveis de ambiente do .env

app = Flask(__name__)

# --- Configurações do Banco de Dados ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Configurações JWT ---
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = 3600 # Token expira em 1 hora (3600 segundos)
jwt = JWTManager(app)

# --- Configurações Google OAuth ---
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
FRONTEND_URL = os.getenv('FRONTEND_URL')

GOOGLE_AUTHORIZATION_BASE_URL = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URL = "https://accounts.google.com/o/oauth2/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v1/userinfo"
GOOGLE_SCOPE = ["https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"]

# --- Configuração de Sessão para OAuth ---
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')

# --- Modelo de Usuário ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)
    google_id = db.Column(db.String(255), unique=True, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    role = db.Column(db.String(50), default='user', nullable=False)
    page_count = db.Column(db.Integer, default=0, nullable=False)

    def __repr__(self):
        return f'<User {self.email}>'

# --- JWT Custom Claims ---
@jwt.user_identity_loader
def user_identity_lookup(user):
    return str(user.id)

@jwt.additional_claims_loader
def add_claims_to_access_token(user):
    user_obj = User.query.get(user.id)
    if user_obj:
        return {'email': user_obj.email, 'role': user_obj.role, 'is_active': user_obj.is_active}
    return {'email': user.email, 'role': 'user', 'is_active': False}

# --- Rotas de Autenticação ---
@app.route('/api/login', methods=['POST'])
def login():
    email = request.json.get('email', None)
    password = request.json.get('password', None)
    if not email or not password:
        return jsonify({"msg": "Email e senha são obrigatórios"}), 400
    user = User.query.filter_by(email=email).first()
    if user and user.password_hash and check_password_hash(user.password_hash, password):
        if not user.is_active:
            return jsonify({"msg": "Sua conta está inativa. Entre em contato com o suporte."}), 403
        access_token = create_access_token(identity=user)
        return jsonify(access_token=access_token), 200
    return jsonify({"msg": "Email ou senha inválidos"}), 401

@app.route('/api/auth/google', methods=['GET'])
def google_auth():
    redirect_uri = url_for('google_callback', _external=True)
    google = OAuth2Session(GOOGLE_CLIENT_ID, scope=GOOGLE_SCOPE, redirect_uri=redirect_uri)
    authorization_url, state = google.authorization_url(GOOGLE_AUTHORIZATION_BASE_URL, access_type="offline", prompt="select_account")
    session['oauth_state'] = state
    return redirect(authorization_url)

@app.route('/api/auth/google/callback', methods=['GET'])
def google_callback():
    if 'error' in request.args:
        return redirect(f"{FRONTEND_URL}/login?error={request.args['error']}")
    if 'oauth_state' not in session or session['oauth_state'] != request.args.get('state'):
        return redirect(f"{FRONTEND_URL}/login?error=InvalidOAuthState")
    redirect_uri = url_for('google_callback', _external=True)
    google = OAuth2Session(GOOGLE_CLIENT_ID, redirect_uri=redirect_uri, state=session['oauth_state'])
    try:
        token = google.fetch_token(GOOGLE_TOKEN_URL, client_secret=GOOGLE_CLIENT_SECRET, authorization_response=request.url)
    except Exception as e:
        print(f"Erro ao buscar token: {e}")
        return redirect(f"{FRONTEND_URL}/login?error=FailedToFetchGoogleToken")
    user_info = google.get(GOOGLE_USERINFO_URL).json()
    email = user_info.get('email')
    google_id = user_info.get('id')
    if not email:
        return redirect(f"{FRONTEND_URL}/login?error=NoEmailFromGoogle")
    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()
        if user:
            user.google_id = google_id
            db.session.commit()
        else:
            user = User(email=email, google_id=google_id, is_active=False, role='user')
            db.session.add(user)
            db.session.commit()
    if not user.is_active:
        return redirect(f"{FRONTEND_URL}/login?error=AccountInactive")
    access_token = create_access_token(identity=user)
    frontend_redirect_url = FRONTEND_URL + f'/login?token={access_token}'
    return redirect(frontend_redirect_url)

# --- Rotas de Administração (Protegidas por JWT e Role) ---
def admin_required():
    def wrapper(fn):
        @functools.wraps(fn)
        @jwt_required()
        def decorator(*args, **kwargs):
            claims = get_jwt()
            if claims.get('role') != 'admin':
                return jsonify({"msg": "Acesso restrito a administradores"}), 403
            return fn(*args, **kwargs)
        return decorator
    return wrapper

@app.route('/api/admin/users', methods=['POST'])
@admin_required()
def create_user():
    email = request.json.get('email', None)
    password = request.json.get('password', None)
    role = request.json.get('role', 'user')
    is_active = request.json.get('is_active', True)
    if not email or not password:
        return jsonify({"msg": "Email e senha são obrigatórios"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "Email já cadastrado"}), 409
    hashed_password = generate_password_hash(password)
    new_user = User(email=email, password_hash=hashed_password, is_active=is_active, role=role)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"msg": f"Usuário {email} criado com sucesso!", "id": new_user.id}), 201

@app.route('/api/admin/users', methods=['GET'])
@admin_required()
def list_users():
    users = User.query.all()
    output = []
    for user in users:
        output.append({
            'id': user.id,
            'email': user.email,
            'google_id': user.google_id is not None,
            'is_active': user.is_active,
            'role': user.role,
            'page_count': user.page_count
        })
    return jsonify(output), 200

@app.route('/api/admin/users/<int:user_id>/status', methods=['PUT'])
@admin_required()
def update_user_status(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "Usuário não encontrado"}), 404

    current_user_id_str = get_jwt_identity()
    current_user_id = int(current_user_id_str) 

    if user.id == current_user_id:
        return jsonify({"msg": "Você não pode alterar o status da sua própria conta."}), 403

    new_status = request.json.get('is_active', None)
    if new_status is None or not isinstance(new_status, bool):
        return jsonify({"msg": "Status 'is_active' inválido ou ausente"}), 400

    user.is_active = new_status
    db.session.commit()
    action = "ativada" if new_status else "desativada"
    return jsonify({"msg": f"Conta do usuário {user.email} {action} com sucesso!"}), 200

# NOVO ENDPOINT: Excluir Usuário
@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required()
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "Usuário não encontrado"}), 404

    current_user_id_str = get_jwt_identity()
    current_user_id = int(current_user_id_str)

    if user.id == current_user_id:
        return jsonify({"msg": "Você não pode excluir sua própria conta."}), 403

    if user.email == 'admin@sistemaponto.com' or user.email == 'admin@example.com':
        other_admins = User.query.filter(User.role == 'admin', User.id != user_id).count()
        if other_admins == 0:
            return jsonify({"msg": "Não é possível excluir o único administrador do sistema."}), 403


    db.session.delete(user)
    db.session.commit()
    return jsonify({"msg": f"Usuário {user.email} excluído com sucesso!"}), 200

@app.route('/api/admin/users/reset-pages', methods=['POST'])
@admin_required()
def reset_all_page_counts():
    try:
        num_updated = User.query.filter(User.role != 'admin').update({User.page_count: 0})
        db.session.commit()
        return jsonify({"msg": f"Contagem de páginas zerada para {num_updated} usuário(s)."}), 200
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao zerar contagem de páginas: {e}")
        return jsonify({"msg": "Ocorreu um erro ao zerar a contagem de páginas."}), 500

@app.route('/api/admin/users/<int:user_id>/reset-pages', methods=['POST'])
@admin_required()
def reset_user_page_count(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "Usuário não encontrado"}), 404
    
    try:
        user.page_count = 0
        db.session.commit()
        return jsonify({"msg": f"Contagem de páginas para {user.email} zerada com sucesso."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": f"Erro ao zerar contagem para o usuário: {str(e)}"}), 500

def create_tables():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(email='admin@example.com').first():
            admin_user = User(
                email='admin@example.com',
                password_hash=generate_password_hash('admin123'),
                is_active=True,
                role='admin'
            )
            db.session.add(admin_user)
            db.session.commit()
            print("Usuário admin padrão criado: admin@example.com / admin123")
