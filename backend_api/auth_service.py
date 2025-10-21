# /opt/pontua/AutoPonto/backend_api/auth_service.py
from flask import Flask, request, jsonify, redirect, session, url_for, g
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required, JWTManager, get_jwt
from datetime import timedelta
import os
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
import requests
import re
import traceback # Import traceback para log de erro detalhado
from functools import wraps

# Carrega variáveis de ambiente
load_dotenv()

app = Flask(__name__)

# Configurações do Banco de Dados
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configurações do JWT
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES_HOURS', '24')))
jwt = JWTManager(app)

# Configurações do Google OAuth
app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.getenv('GOOGLE_CLIENT_SECRET')
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY') # Necessário para a sessão do OAuth
oauth = OAuth(app)

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

db = SQLAlchemy(app)
migrate = Migrate(app, db)

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=True)
    role = db.Column(db.String(50), nullable=False, default='user')
    is_active = db.Column(db.Boolean, default=True)
    page_count = db.Column(db.Integer, default=0)
    plan_status = db.Column(db.String(50), nullable=True, default='free')
    # name = db.Column(db.String(100), nullable=True) # Descomente se adicionar nome

# Função para adicionar claims personalizadas ao token (CORRIGIDO)
@jwt.additional_claims_loader # <-- CORRIGIDO
def add_claims_to_access_token(identity):
    user = User.query.filter_by(email=identity).first()
    if user:
        return {
            'role': user.role,
            'is_active': user.is_active,
            'plan_status': user.plan_status or 'free'
        }
    return {}

# Decorator para exigir role de admin (CORRIGIDO)
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

# Função para verificar se o token está na blocklist (para logout)
@jwt.token_in_blocklist_loader
def check_if_token_in_blocklist(jwt_header, jwt_payload):
    # Implementação básica, pode ser substituída por Redis/DB se necessário
    return False

@app.route('/api/login', methods=['POST'])
def login():
    email = request.json.get('email', None)
    password = request.json.get('password', None)

    if not email or not password:
        return jsonify({"msg": "Email e senha são obrigatórios"}), 400

    user = User.query.filter_by(email=email).first()

    # Verifica se o usuário existe e se tem hash de senha (para logins via Google não quebrar)
    if user and user.password_hash:
        try:
            if check_password_hash(user.password_hash, password):
                if not user.is_active:
                    return jsonify({"msg": "Sua conta está inativa. Entre em contato com o suporte."}), 403

                access_token = create_access_token(identity=email)
                return jsonify(access_token=access_token), 200
            else:
                 # Senha incorreta
                 return jsonify({"msg": "Email ou senha inválidos"}), 401
        except ValueError as e:
            # Captura erro de hash inválido, como o 'Invalid hash method'
            print(f"Erro ao verificar hash para {email}: {e}")
            return jsonify({"msg": "Erro interno ao verificar senha. Contate o suporte."}), 500
    elif user and not user.password_hash:
        # Usuário existe mas provavelmente cadastrou via Google e não tem senha definida
        return jsonify({"msg": "Login com senha não disponível. Use o login com Google."}), 401
    else:
        # Usuário não encontrado
        return jsonify({"msg": "Email ou senha inválidos"}), 401

# --- ROTA DE CADASTRO ---
@app.route('/api/register', methods=['POST'])
def register():
    email = request.json.get('email', None)
    password = request.json.get('password', None)
    name = request.json.get('name', None) # Captura o nome

    if not email or not password:
        return jsonify({"msg": "Email e senha são obrigatórios"}), 400

    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
         return jsonify({"msg": "Formato de e-mail inválido"}), 400

    if len(password) < 6:
        return jsonify({"msg": "Senha precisa ter pelo menos 6 caracteres"}), 400
    if not re.search(r"\d", password):
         return jsonify({"msg": "Senha precisa ter pelo menos 1 número"}), 400
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return jsonify({"msg": "Senha precisa ter pelo menos 1 caractere especial"}), 400

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
        plan_status='free' # Começa como 'free' para forçar escolha
    )

    db.session.add(new_user)
    try:
        db.session.commit()
        return jsonify({"msg": f"Usuário {email} criado com sucesso! Faça o login."}), 201
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao registrar usuário: {e}")
        return jsonify({"msg": "Erro interno ao criar usuário."}), 500

# Rota de login do Google
@app.route('/api/auth/google')
def google_login():
    redirect_uri = url_for('google_authorize', _external=True)
    state = os.urandom(16).hex()
    session['oauth_state'] = state
    return google.authorize_redirect(redirect_uri, state=state)

# Rota de callback do Google
@app.route('/api/auth/google/callback')
def google_authorize():
    try:
        state = session.pop('oauth_state', None)
        if state is None or state != request.args.get('state'):
             print("Erro de state OAuth: state da sessão é None ou não bate.")
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

    if not user:
        # Usuário Google não encontrado no DB -> Redireciona com erro
        # Poderia criar o usuário aqui, mas por segurança, redireciona
        return redirect(f"{os.getenv('FRONTEND_URL', '/')}/login?error=UserNotFound")

    if not user.is_active:
        return redirect(f"{os.getenv('FRONTEND_URL', '/')}/login?error=AccountInactive")

    # Usuário encontrado e ativo, gera o token JWT
    access_token = create_access_token(identity=google_email)

    # Redireciona para o frontend com o token
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
        email=user.email,
        role=claims.get('role', 'user'),
        is_active=claims.get('is_active', False),
        page_count=user.page_count,
        plan_status=claims.get('plan_status', 'free') # Retorna o plano do token
    ), 200

# Rota de atualização de senha pelo próprio usuário
@app.route('/api/user/password', methods=['PUT'])
@jwt_required()
def update_password():
    current_user_email = get_jwt_identity()
    user = User.query.filter_by(email=current_user_email).first()

    if not user:
        return jsonify({"msg": "Usuário não encontrado"}), 404

    current_password = request.json.get('currentPassword')
    new_password = request.json.get('newPassword')

    if not current_password or not new_password:
        return jsonify({"msg": "Senha atual e nova senha são obrigatórias"}), 400

    # Verifica se o usuário tem hash (pode não ter se for conta Google)
    if not user.password_hash:
         return jsonify({"msg": "Não é possível alterar senha de contas criadas via Google."}), 400

    try:
        if not check_password_hash(user.password_hash, current_password):
            return jsonify({"msg": "Senha atual incorreta"}), 401
    except ValueError as e:
         print(f"Erro ao verificar hash (update_password) para {current_user_email}: {e}")
         return jsonify({"msg": "Erro interno ao verificar senha. Contate o suporte."}), 500

    # Validação da nova senha
    if len(new_password) < 6:
        return jsonify({"msg": "Nova senha precisa ter pelo menos 6 caracteres"}), 400
    if not re.search(r"\d", new_password):
         return jsonify({"msg": "Nova senha precisa ter pelo menos 1 número"}), 400
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", new_password):
        return jsonify({"msg": "Nova senha precisa ter pelo menos 1 caractere especial"}), 400

    user.password_hash = generate_password_hash(new_password)
    db.session.commit()

    return jsonify({"msg": "Senha atualizada com sucesso"}), 200

# --- ROTAS DE ADMINISTRAÇÃO ---

# Rota de administração para buscar usuários (ATUALIZADA com sort/filter)
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

        valid_sort_columns = {
            'id': User.id,
            'email': User.email,
            'status': User.is_active, # Sort by boolean status
            'role': User.role,
            'plan': User.plan_status,
            'pages': User.page_count
        }

        sort_column = valid_sort_columns.get(sort_by, User.id)

        if sort_order.lower() == 'desc':
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        users = pagination.items

        return jsonify({
            "users": [
                {
                    "id": user.id,
                    "email": user.email,
                    "role": user.role,
                    "is_active": user.is_active,
                    "page_count": user.page_count,
                    "plan_status": user.plan_status or 'free'
                } for user in users
            ],
            "total_pages": pagination.pages,
            "current_page": page,
            "total_users": pagination.total
        }), 200

    except Exception as e:
        print(f"Erro ao buscar usuários: {e}")
        traceback.print_exc() # Print full traceback
        return jsonify({"msg": "Erro interno ao buscar usuários"}), 500


# Rota de administração para atualizar status (ATIVAR/DESATIVAR)
@app.route('/api/admin/users/<int:user_id>/status', methods=['PUT'])
@admin_required()
def update_user_status(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "Usuário não encontrado"}), 404

    # Verifica se o admin está tentando desativar a si mesmo
    claims = get_jwt()
    current_admin_email = get_jwt_identity()
    if user.email == current_admin_email:
        return jsonify({"msg": "Não pode alterar o status da sua própria conta."}), 403

    is_active_data = request.json.get('is_active')
    if is_active_data is None or not isinstance(is_active_data, bool):
        return jsonify({"msg": "Campo 'is_active' (booleano) é obrigatório."}), 400

    user.is_active = is_active_data

    try:
        db.session.commit()
        return jsonify({"msg": f"Status do usuário {user.email} atualizado para {'Ativo' if user.is_active else 'Inativo'}."}), 200
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao atualizar status do usuário {user_id}: {e}")
        return jsonify({"msg": "Erro interno ao salvar alteração de status."}), 500


# Rota de administração para atualizar dados gerais do usuário (incluindo senha)
@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@admin_required()
def update_user_details(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "Usuário não encontrado"}), 404

    data = request.json

    # Atualizar Email (com verificação)
    if 'email' in data and data['email'] != user.email:
        new_email = data['email']
        if not re.match(r"[^@]+@[^@]+\.[^@]+", new_email):
             return jsonify({"msg": "Formato de e-mail inválido"}), 400
        existing_user = User.query.filter(User.email == new_email, User.id != user_id).first()
        if existing_user:
            return jsonify({"msg": "Email já está em uso por outra conta"}), 409
        user.email = new_email

    # Atualizar Role
    if 'role' in data:
         # Impede rebaixar o próprio admin logado? (Opcional mas seguro)
         claims = get_jwt()
         current_admin_email = get_jwt_identity()
         if user.email == current_admin_email and data['role'] != 'admin':
              return jsonify({"msg": "Não pode alterar seu próprio nível para não-admin."}), 403
         user.role = data['role']

    # Atualizar Status (mas usa a rota /status para isso normalmente)
    if 'is_active' in data and isinstance(data['is_active'], bool):
         if user.email == get_jwt_identity(): # Re-verifica se é o próprio admin
              return jsonify({"msg": "Não pode alterar seu próprio status aqui. Use a interface padrão."}), 403
         user.is_active = data['is_active']

    # Atualizar Contagem de Páginas
    if 'page_count' in data:
        try:
            count = int(data['page_count'])
            if count < 0: raise ValueError("Contagem não pode ser negativa")
            user.page_count = count
        except (ValueError, TypeError):
            return jsonify({"msg": "Contagem de páginas deve ser um número inteiro não negativo."}), 400

    # Atualizar Plano
    if 'plan_status' in data:
        user.plan_status = data['plan_status']

    # Atualização de Senha pelo Admin (via modal)
    if 'new_password' in data and data['new_password']:
        new_pass = data['new_password']
        # Validação de senha pode ser opcional para admin, ou usar a mesma do cadastro
        if len(new_pass) < 6:
             return jsonify({"msg": "Nova senha precisa ter pelo menos 6 caracteres"}), 400
        # Adicione outras validações se desejar
        user.password_hash = generate_password_hash(new_pass)

    try:
        db.session.commit()
        # Retorna os dados atualizados do usuário
        return jsonify({
            "msg": f"Dados do usuário {user.email} atualizados com sucesso.",
            "user": {
                "id": user.id,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
                "page_count": user.page_count,
                "plan_status": user.plan_status or 'free'
            }
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao atualizar dados do usuário {user_id}: {e}")
        traceback.print_exc()
        return jsonify({"msg": "Erro interno ao salvar alterações nos dados do usuário."}), 500


# Rota de administração para EXCLUIR um usuário
@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required()
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "Usuário não encontrado"}), 404

    # Impede exclusão do próprio admin logado
    current_admin_email = get_jwt_identity()
    if user.email == current_admin_email:
        return jsonify({"msg": "Não pode excluir sua própria conta."}), 403

    try:
        db.session.delete(user)
        db.session.commit()
        return jsonify({"msg": f"Usuário {user.email} excluído com sucesso."}), 200
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao excluir usuário {user_id}: {e}")
        return jsonify({"msg": "Erro interno ao excluir usuário."}), 500


# Rota para zerar contagem de páginas de um usuário específico
@app.route('/api/admin/users/<int:user_id>/reset-pages', methods=['POST'])
@admin_required()
def reset_user_page_count(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "Usuário não encontrado"}), 404

    user.page_count = 0
    try:
        db.session.commit()
        return jsonify({"msg": f"Contagem de páginas para {user.email} zerada com sucesso."}), 200
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao zerar contagem do usuário {user_id}: {e}")
        return jsonify({"msg": "Erro interno ao zerar contagem."}), 500


# Rota para zerar contagem de páginas de TODOS os usuários não-admin
@app.route('/api/admin/users/reset-pages', methods=['POST'])
@admin_required()
def reset_all_non_admin_page_counts():
    try:
        # Atualiza todos os usuários onde role != 'admin'
        updated_count = User.query.filter(User.role != 'admin').update({User.page_count: 0})
        db.session.commit()
        return jsonify({"msg": f"Contagem de páginas zerada para {updated_count} usuários (não-admins)."}), 200
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao zerar contagem geral: {e}")
        return jsonify({"msg": "Erro interno ao zerar contagem geral."}), 500


# --- FIM DAS ROTAS DE ADMINISTRAÇÃO ---
