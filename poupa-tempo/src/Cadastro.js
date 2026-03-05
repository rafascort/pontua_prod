// /opt/pontua/AutoPonto/poupa-tempo/src/Cadastro.js
import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './Cadastro.css'; // Importa o CSS

const Cadastro = () => {
  const [name, setName] = useState(''); // Estado para o nome
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [erro, setErro] = useState('');
  const [sucesso, setSucesso] = useState(''); // Estado para mensagem de sucesso
  const navigate = useNavigate();

  const handleCadastro = async (e) => {
    e.preventDefault();
    setErro('');
    setSucesso('');

    // Validação básica no frontend (pode ser mais robusta)
    if (password !== confirmPassword) {
      setErro('As senhas não coincidem.');
      return;
    }
    // Validação de senha no frontend (espelha o backend)
    if (password.length < 6) {
        setErro('Senha precisa ter pelo menos 6 caracteres.'); return;
    }
    if (!/\d/.test(password)) {
          setErro('Senha precisa ter pelo menos 1 número.'); return;
    }
    if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) {
          setErro('Senha precisa ter pelo menos 1 caractere especial.'); return;
    }

    try {
      const response = await fetch('/api/register', { // Chama a nova rota
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        // Inclui o nome no body
        body: JSON.stringify({ name, email, password }),
      });

      const data = await response.json(); // Lê a resposta JSON

      if (response.ok) {
        setSucesso(data.msg || 'Cadastro realizado com sucesso! Redirecionando para login...');
        // Limpa os campos
        setName('');
        setEmail('');
        setPassword('');
        setConfirmPassword('');
        // Redireciona para o login após um breve delay
        setTimeout(() => {
          navigate('/login');
        }, 2000); // Espera 2 segundos
      } else {
        setErro(data.msg || 'Erro ao realizar cadastro.');
      }
    } catch (error) {
      console.error("Erro de rede ao tentar cadastrar:", error);
      setErro('Não foi possível conectar ao servidor. Verifique sua conexão.');
    }
  };

  // Lógica da mensagem dinâmica do WhatsApp para o cadastro
  const mensagemWhatsapp = `Olá! Meu nome é ${name || '________'}, estou na tela de cadastro do Sistema Ponto e tenho uma dúvida.`;
  const linkWhatsapp = `https://wa.me/5554999427282?text=${encodeURIComponent(mensagemWhatsapp)}`;

  return (
    <div className="login-container"> {/* Reutiliza container do login para o fundo */}
      <div className="cadastro-card"> {/* Usa a classe específica para o card */}
        <div className="cadastro-header">
          <h2>Criar Conta</h2>
        </div>
        <form onSubmit={handleCadastro} className="cadastro-form">
          {/* Campo Nome */}
          <div className="input-group">
            <label htmlFor="name">Nome Completo</label>
            <input
              type="text"
              id="name"
              placeholder="Digite seu nome"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          {/* Campo Email */}
          <div className="input-group">
            <label htmlFor="email">E-mail</label>
            <input
              type="email"
              id="email"
              placeholder="Digite seu e-mail"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          {/* Campo Senha */}
          <div className="input-group">
            <label htmlFor="password">Senha</label>
            <input
              type="password"
              id="password"
              placeholder="Mín. 6 caracteres, 1 número, 1 especial"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          {/* Campo Confirmar Senha */}
          <div className="input-group">
            <label htmlFor="confirmPassword">Confirmar Senha</label>
            <input
              type="password"
              id="confirmPassword"
              placeholder="Repita sua senha"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
            />
          </div>

          {/* Exibe mensagem de erro ou sucesso */}
          {erro && <p className="error-message">{erro}</p>}
          {sucesso && <p className="success-message">{sucesso}</p>}

          <button type="submit" disabled={!!sucesso}> {/* Desabilita botão após sucesso */}
            Cadastrar
          </button>
        </form>
        <div className="login-link">
          Já tem uma conta? <Link to="/login">Faça Login</Link>
        </div>

        {/* Bloco de Suporte via WhatsApp adicionado no final do card */}
        <div style={{ marginTop: '20px', textAlign: 'center', fontSize: '14px', borderTop: '1px solid #eee', paddingTop: '15px' }}>
          <span style={{ color: '#666' }}>Dúvidas no cadastro?</span>
          <a 
            href={linkWhatsapp}
            target="_blank" 
            rel="noopener noreferrer"
            style={{ color: '#25D366', fontWeight: 'bold', marginLeft: '5px', textDecoration: 'none' }}
          >
            Fale conosco no WhatsApp
          </a>
        </div>
      </div>
    </div>
  );
};

export default Cadastro;
