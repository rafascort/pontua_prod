// src/App.js
import React, { useState, useEffect } from 'react';
// REMOVIDO: BrowserRouter (porque ele vai para index.js)
// APENAS O QUE É USADO DENTRO DO APP:
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'; 
import Login from './Login';
import MainApp from './MainApp';
import AdminDashboard from './AdminDashboard';
import './App.css';
import useRemoveNBSP from './hooks/useRemoveNBSP';

function App() {
    useRemoveNBSP();
    const [logado, setLogado] = useState(false);
    const [isAdmin, setIsAdmin] = useState(false);
    const navigate = useNavigate(); // AGORA ESTÁ DENTRO DO CONTEXTO DO ROUTER (vindo de index.js)

    // Função para decodificar o token e definir estados
    const decodeAndSetUserStatus = (token) => {
        if (token) {
            try {
                const base64Url = token.split('.')[1];
                const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
                const decodedToken = JSON.parse(window.atob(base64));
                setLogado(decodedToken.is_active);
                setIsAdmin(decodedToken.role === 'admin' && decodedToken.is_active);
                return decodedToken.role;
            } catch (e) {
                console.error("Erro ao decodificar token JWT:", e);
                localStorage.removeItem('jwt_token');
                setLogado(false);
                setIsAdmin(false);
            }
        } else {
            setLogado(false);
            setIsAdmin(false);
        }
        return null;
    };

    useEffect(() => {
        const token = localStorage.getItem('jwt_token');
        decodeAndSetUserStatus(token);
    }, []);

    const handleLoginSuccess = () => {
        const token = localStorage.getItem('jwt_token');
        decodeAndSetUserStatus(token);
    };

    const handleLogout = () => {
        localStorage.removeItem('jwt_token');
        setLogado(false);
        setIsAdmin(false);
        navigate('/login', { replace: true });
    };

    return (
        // REMOVIDO: <BrowserRouter>
        <Routes> {/* <--- App RETORNA DIRETAMENTE AS ROTAS */}
            <Route path="/login" element={<Login onLogin={handleLoginSuccess} />} />

            <Route
                path="/app"
                element={logado ? <MainApp onLogout={handleLogout} /> : <Navigate to="/login" replace />}
            />

            <Route
                path="/admin"
                element={logado && isAdmin ? <AdminDashboard onLogout={handleLogout} /> : <Navigate to="/login" replace />}
            />

            <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
        // REMOVIDO: </BrowserRouter>
    );
}

export default App;

