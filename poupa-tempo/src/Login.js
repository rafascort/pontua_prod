// /opt/pontua/AutoPonto/poupa-tempo/src/Login.js
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './style.css'; // Assume que os estilos estão corretos

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

      // Importante: A verificação de is_active AGORA é feita ANTES de salvar o token
      if (!decodedToken.is_active) {
        setErro('Sua conta está inativa. Entre em contato com o suporte.');
        localStorage.removeItem('jwt_token'); // Não salva token de conta inativa
        // Não chama onLogin()
        navigate('/login', { replace: true }); // Permanece na página de login
        return;
      }

      // Se ativo, salva o token e chama o callback de sucesso
      localStorage.setItem('jwt_token', token);
      onLogin(); // Notifica o App.js sobre o login bem-sucedido

      // Navega para a aplicação principal
      // A lógica de redirecionar para /admin se for admin pode ser feita no App.js
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
      const errorParam = params.get('error'); // Pega o parâmetro de erro

      if (token) {
          // Se houver um token na URL (vindo do Google callback), tenta usá-lo
          decodeAndNavigate(token);
          // Limpa o token da URL após tentar usá-lo
          window.history.replaceState(null, '', window.location.pathname);
      } else if (errorParam) {
           // Mapeia os erros da URL para mensagens amigáveis
           let errorMessage = 'Ocorreu um erro durante o login.';
           if (errorParam === 'UserNotFound') {
               errorMessage = 'Conta Google não registada no sistema. Contacte o administrador.';
           } else if (errorParam === 'AccountInactive') {
               errorMessage = 'A sua conta está inativa. Contacte o administrador.';
           } else if (errorParam === 'NoEmailFromGoogle') {
                errorMessage = 'Não foi possível obter o seu email do Google.';
           } else if (errorParam === 'FailedToFetchGoogleToken') {
                errorMessage = 'Falha ao comunicar com o Google. Tente novamente.';
           } else if (errorParam === 'InvalidOAuthState') {
               errorMessage = 'Erro de segurança na autenticação. Tente novamente.';
           }
           setErro(errorMessage);

           // Limpa o parâmetro de erro da URL
           window.history.replaceState(null, '', window.location.pathname);
      }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Executa apenas uma vez ao montar

  const handleLogin = async (e) => {
    e.preventDefault();
    setErro(''); // Limpa erros anteriores
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
        // A função decodeAndNavigate tratará de salvar o token, chamar onLogin e navegar
        decodeAndNavigate(data.access_token);
      } else {
        const errorData = await response.json();
        setErro(errorData.msg || 'Erro ao autenticar. Verifique email e senha.');
      }
    } catch (error) {
      console.error("Erro de rede ao tentar login:", error);
      setErro('Não foi possível conectar ao servidor. Verifique sua conexão e tente novamente.');
    }
  };

  const handleGoogleLogin = () => {
    // Redireciona para o endpoint do backend que inicia o fluxo OAuth
    window.location.href = '/api/auth/google';
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <h2>Sistema Ponto</h2>
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
          {/* O link de esqueci a senha pode ser implementado futuramente */}
          {/* <div className="forgot-password">
            <a href="#">Esqueci minha senha</a>
          </div> */}
          {erro && <p className="error-message">{erro}</p>}
          <button type="submit">Autenticar</button>
        </form>
        {/* Separador visual opcional */}
        {/* <div style={{ textAlign: 'center', color: '#a8b3c7', margin: '20px 0' }}>OU</div> */}
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
