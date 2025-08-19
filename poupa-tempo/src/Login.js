import React, { useState } from 'react';
import './style.css';

const Login = ({ onLogin }) => {
  const [usuario, setUsuario] = useState('');
  const [senha, setSenha] = useState('');
  const [erro, setErro] = useState('');

  const handleLogin = (e) => {
    e.preventDefault();
    if (usuario === 'admin' && senha === '1990') {
      onLogin();
    } else {
      setErro('Usuário ou senha inválidos');
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <h2>Pontua</h2>
          <p>Automação de Cartão Ponto</p>
          <small>Sistema Seguro</small>
        </div>

        <form onSubmit={handleLogin} className="login-form">
          <div className="input-group">
            <label>Usuário</label>
            <input
              type="text"
              placeholder="Digite seu usuário"
              value={usuario}
              onChange={(e) => setUsuario(e.target.value)}
            />
          </div>

          <div className="input-group">
            <label>Senha</label>
            <input
              type="password"
              placeholder="Digite sua senha"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
            />
          </div>

          <div className="forgot-password">
            <a href="#">Esqueci minha senha</a>
          </div>

          {erro && <p className="error-message">{erro}</p>}

          <button type="submit">Autenticar</button>
        </form>

        <div className="login-footer">
          <span>24/7</span>
          <span>Criptografado</span>
        </div>
      </div>
    </div>
  );
};

export default Login;