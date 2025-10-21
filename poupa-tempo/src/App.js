// /opt/pontua/AutoPonto/poupa-tempo/src/App.js
import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import Login from './Login';
import MainApp from './MainApp';
import AdminDashboard from './AdminDashboard';
import LandingPage from './LandingPage'; // Importado na etapa anterior
import Cadastro from './Cadastro'; // <-- 1. IMPORTAR CADASTRO
import Planos from './Planos'; // <-- 2. IMPORTAR PLANOS
import './App.css';
import './LandingPage.css'; // Importado na etapa anterior
import './Cadastro.css'; // <-- 3. IMPORTAR CSS CADASTRO
import './Planos.css'; // <-- 4. IMPORTAR CSS PLANOS
import useRemoveNBSP from './hooks/useRemoveNBSP';
import { isTokenValid, decodeToken } from './authUtils'; 
import { setUnauthorizedCallback } from './apiUtils'; 

function App() {
    useRemoveNBSP();
    const [logado, setLogado] = useState(false); 
    const [isAdmin, setIsAdmin] = useState(false);
    const navigate = useNavigate();
    const location = useLocation(); 

    const handleUnauthorized = () => {
        // Modificado para não deslogar se estiver na landing page ou cadastro
        if (!logado && (location.pathname === '/login' || location.pathname === '/' || location.pathname === '/cadastro')) return;


        console.log("Executando handleUnauthorized (logout forçado)");
        localStorage.removeItem('jwt_token');
        setLogado(false);
        setIsAdmin(false);
        navigate('/login?sessionExpired=true', { replace: true });
    };

    useEffect(() => {
        setUnauthorizedCallback(handleUnauthorized);

        if (isTokenValid()) {
            const token = localStorage.getItem('jwt_token');
            const decoded = decodeToken(token); 
            setLogado(true);
            setIsAdmin(decoded?.role === 'admin');
        } else {
            // Se token inválido, não força logout se estiver em páginas públicas
            if (location.pathname !== '/login' && location.pathname !== '/' && location.pathname !== '/cadastro') {
                handleUnauthorized();
            } else {
                 setLogado(false);
                 setIsAdmin(false);
            }
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []); 

    const handleLoginSuccess = () => {
        if (isTokenValid()) {
            const token = localStorage.getItem('jwt_token');
            const decoded = decodeToken(token);
            setLogado(true);
            setIsAdmin(decoded?.role === 'admin');
            // A navegação agora é feita 100% dentro do Login.js
        } else {
             handleUnauthorized();
        }
    };

     const handleLogout = () => {
        console.log("Executando handleLogout (manual)");
        localStorage.removeItem('jwt_token');
        setLogado(false);
        setIsAdmin(false);
        navigate('/login', { replace: true });
    };

    const ProtectedRoute = ({ children, requireAdmin = false }) => {
        if (!logado) {
            return <Navigate to="/login?redirected=true" replace />;
        }
        if (requireAdmin && !isAdmin) {
             console.warn("Tentativa de acesso não autorizado à rota de admin.");
             return <Navigate to="/app" replace />; 
        }
        return children;
    };


    return (
        <Routes>
            {/* --- ROTAS PÚBLICAS --- */}
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<Login onLogin={handleLoginSuccess} />} />
            <Route path="/cadastro" element={<Cadastro />} /> {/* <-- 5. ROTA DE CADASTRO */}


            {/* --- ROTAS PROTEGIDAS --- */}
            
            {/* Rota para a aplicação principal (Protegida) */}
            <Route
                path="/app"
                element={
                    <ProtectedRoute>
                        <MainApp onLogout={handleLogout} isAdmin={isAdmin} />
                    </ProtectedRoute>
                }
            />

            {/* Rota para o painel de administração (Protegida) */}
            <Route
                path="/admin"
                element={
                    <ProtectedRoute requireAdmin={true}>
                        <AdminDashboard onLogout={handleLogout} />
                    </ProtectedRoute>
                }
            />

            {/* Rota para a página de Planos (Protegida) */}
            <Route
                path="/planos"
                element={
                    <ProtectedRoute>
                        {/* Passa onLogout para o usuário poder sair da tela de planos */}
                        <Planos onLogout={handleLogout} />
                    </ProtectedRoute>
                }
            />

            {/* Redireciona qualquer outra rota para a Landing Page (/) */}
            <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
    );
}

export default App;
