import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './Login';
import MainApp from './MainApp';
import './App.css';

function App() {
    const [logado, setLogado] = useState(() => {
        return localStorage.getItem('logado') === 'true';
    });

    const handleLoginSuccess = () => {
        setLogado(true);
        localStorage.setItem('logado', 'true');
    };

    const handleLogout = () => {
        setLogado(false);
        localStorage.setItem('logado', 'false');
    };

    return (
        <BrowserRouter>
            <Routes>
                <Route path="/login" element={<Login onLogin={handleLoginSuccess} />} />
                <Route path="/app" element={logado ? <MainApp onLogout={handleLogout} /> : <Navigate to="/login" replace />} />
                <Route path="*" element={<Navigate to="/login" replace />} />
            </Routes>
        </BrowserRouter>
    );
}

export default App;

