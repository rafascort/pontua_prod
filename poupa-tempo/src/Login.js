import React, { useState } from 'react';
import './style.css';

const Login = ({ onLogin }) => {
  const [usuario, setUsuario] = useState('');
  const [senha, setSenha] = useState('');
  const [erro, setErro] = useState('');

  const handleLogin = (e) => {
    e.preventDefault();
    if (usuario === 'admin' && senha === '1990') {
      onLogin(); // chama a função de login
    } else {
      setErro('Usuário ou senha inválidos');
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <div className="login-icon">🔑</div>
          <h2>Pontua</h2>
          <p>Atutomação de Cartão Ponto</p>
        </div>
        <form onSubmit={handleLogin} className="login-form">
          <label>Usuário</label>
          <input
            type="text"
            placeholder="Digite seu usuário"
            value={usuario}
            onChange={(e) => setUsuario(e.target.value)}
          />
          <label>Senha</label>
          <input
            type="password"
            placeholder="Digite sua senha"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
          />
          <small style={{ color: 'blue', marginTop: '4px' }}>
            Esqueci minha senha
          </small>
          {erro && <p style={{ color: 'red' }}>{erro}</p>}
          <button type="submit">🔐 Autenticar</button>
        </form>
      </div>
    </div>
  );
};

export default Login;
