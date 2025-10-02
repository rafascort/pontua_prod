// src/Login.js
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './style.css';

const Login = ({ onLogin }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [erro, setErro] = useState('');
  const navigate = useNavigate();

  // Função auxiliar para decodificar o token e navegar
  const decodeAndNavigate = (token) => {
    try {
      const base64Url = token.split('.')[1];
      const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
      const decodedToken = JSON.parse(window.atob(base64));

      if (!decodedToken.is_active) {
        setErro('Sua conta está inativa. Entre em contato com o suporte para ativá-la.');
        localStorage.removeItem('jwt_token'); 
        onLogin();
        navigate('/login', { replace: true }); 
        return;
      }

      localStorage.setItem('jwt_token', token);
      onLogin();

      // --- ALTERAÇÃO APLICADA AQUI ---
      // Todos os usuários, incluindo admins, são redirecionados para a tela principal.
      navigate('/app', { replace: true });

    } catch (e) {
      console.error("Erro ao decodificar token JWT para navegação:", e);
      setErro('Erro ao processar token de login. Tente novamente.');
      localStorage.removeItem('jwt_token');
      navigate('/login', { replace: true });
    }
  };

  useEffect(() => {
      const params = new URLSearchParams(window.location.search);
      const token = params.get('token');
      if (token) {
          decodeAndNavigate(token);
      }
  }, [onLogin, navigate]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setErro('');
    try {
      const response = await fetch('/api/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password }),
      });

      if (response.ok) {
        const data = await response.json();
        decodeAndNavigate(data.access_token);
      } else {
        const errorData = await response.json();
        setErro(errorData.msg || 'Erro ao autenticar.');
      }
    } catch (error) {
      console.error("Erro de rede ao tentar login:", error);
      setErro('Não foi possível conectar ao servidor. Tente novamente.');
    }
  };

  const handleGoogleLogin = () => {
    window.location.href = '/api/auth/google';
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
            <label>E-mail</label>
            <input
              type="email"
              placeholder="Digite seu e-mail"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="input-group">
            <label>Senha</label>
            <input
              type="password"
              placeholder="Digite sua senha"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <div className="forgot-password">
            <a href="#">Esqueci minha senha</a>
          </div>
          {erro && <p className="error-message">{erro}</p>}
          <button type="submit">Autenticar</button>
        </form>
        <button onClick={handleGoogleLogin} className="google-login-button">
          Login com Google
        </button>
        <div className="login-footer">
          <span>24/7</span>
          <span>Criptografado</span>
        </div>
      </div>
    </div>
  );
};

export default Login;
