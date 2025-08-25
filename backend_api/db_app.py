from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import bcrypt

app = Flask(__name__)

# Configure a string de conexão do banco de dados
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:Bomdiaes3@localhost:5432/sistema_autenticacao'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Modelo de Usuário
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.LargeBinary, nullable=False)

# Rota de Registro
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    hashed = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt())
    new_user = User(username=data['username'], password=hashed)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"message": "Usuário registrado com sucesso!"}), 201

# Rota de Login
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(username=data['username']).first()
    if user and bcrypt.checkpw(data['password'].encode('utf-8'), user.password):
        return jsonify({"message": "Login bem-sucedido!"}), 200
    return jsonify({"error": "Credenciais inválidas!"}), 401

# Rota para listar usuários
@app.route('/api/users', methods=['GET'])
def list_users():
    users = User.query.all()  # Consulta todos os usuários
    user_list = [{"id": user.id, "username": user.username} for user in users]  # Cria uma lista de dicionários
    return jsonify(user_list), 200  # Retorna a lista em formato JSON

# Criar Tabelas
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)  # Usando a porta 5003

