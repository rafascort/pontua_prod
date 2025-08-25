// src/Login.js
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom'; 
import './style.css';

const Login = ({ onLogin }) => {
  const [usuario, setUsuario] = useState('');
  const [senha, setSenha] = useState('');
  const [erro, setErro] = useState('');
  const [isLoading, setIsLoading] = useState(false); // Novo estado para controle de loading
  const navigate = useNavigate(); 

  const handleLogin = async (e) => {
    e.preventDefault();
    setErro(''); 
    setIsLoading(true); // Inicia o loading ao enviar o formulário

    try {
      const response = await fetch('http://localhost:5003/api/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username: usuario, password: senha }),
      });

      setIsLoading(false); // Encerra o loading após resposta

      if (response.ok) {
        const result = await response.json();
        onLogin(); 
        navigate('/app', { replace: true }); 
      } else {
        const error = await response.json();
        setErro(error.error || 'Erro ao fazer login'); // Mensagem de erro padrão
      }
    } catch (err) {
      setIsLoading(false);
      setErro('Erro ao tentar conectar-se ao servidor.'); 
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
              required // Adiciona validação requerida
            />
          </div>
          <div className="input-group">
            <label>Senha</label>
            <input
              type="password"
              placeholder="Digite sua senha"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              required // Adiciona validação requerida
            />
          </div>
          <div className="forgot-password">
            <a href="#">Esqueci minha senha</a>
          </div>
          {erro && <p className="error-message">{erro}</p>} {/* Exibe mensagem de erro */}
          <button type="submit" disabled={isLoading}>{isLoading ? 'Carregando...' : 'Autenticar'}</button> {/* Feedback de loading */}
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

