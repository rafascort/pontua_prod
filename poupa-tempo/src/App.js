// src/App.js
import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './Login';
import MainApp from './MainApp'; // Importe o novo componente MainApp
import './App.css'; // Mantenha o CSS global, se necessário

function App() {
  // O estado de autenticação agora vive aqui no componente App principal
  const [logado, setLogado] = useState(false); 

  const handleLoginSuccess = () => {
    setLogado(true);
  };

  // Se precisar de uma função de logout, adicione aqui
  // const handleLogout = () => {
  //   setLogado(false);
  // };

  return (
    <BrowserRouter>
      <Routes>
        {/* Rota para a página de login */}
        <Route 
          path="/login"
          element={<Login onLogin={handleLoginSuccess} />}
        />

        {/* Rota para a aplicação principal, protegida por autenticação */}
        <Route 
          path="/app"
          element={logado ? <MainApp /> : <Navigate to="/login" replace />}
        />

        {/* Redirecionamento padrão: qualquer outra rota vai para /login */}
        <Route 
          path="*"
          element={<Navigate to="/login" replace />}
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
