// /opt/pontua/AutoPonto/poupa-tempo/src/App.js
import React, { useState, useEffect, useCallback } from 'react';
// REMOVIDO: import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Routes, Route, Navigate } from 'react-router-dom'; // <-- MANTÉM Routes, Route, Navigate
import { getToken, removeToken, decodeToken } from './authUtils';
import { fetchWithAuth, setUnauthorizedCallback } from './apiUtils';
import LandingPage from './LandingPage';
import Login from './Login';
import Cadastro from './Cadastro';
import MainApp from './MainApp';
import AdminDashboard from './AdminDashboard';
import Planos from './Planos';
import PaymentSuccess from './PaymentSuccess';
import './App.css';
import './style.css';
import 'react-toastify/dist/ReactToastify.css';

function App() {
    const [logado, setLogado] = useState(!!getToken());
    const [isAdmin, setIsAdmin] = useState(false);
    const [planStatus, setPlanStatus] = useState('free');
    const [isLoadingUser, setIsLoadingUser] = useState(true);

    const handleUnauthorized = useCallback(() => {
        console.log("Sessão expirada ou inválida. Fazendo logout.");
        removeToken();
        setLogado(false);
        setIsAdmin(false);
        setPlanStatus('free');
        setIsLoadingUser(false);
    }, []);

    useEffect(() => {
        setUnauthorizedCallback(handleUnauthorized);
    }, [handleUnauthorized]);

    const fetchUserData = useCallback(async () => {
        setIsLoadingUser(true);
        const token = getToken();
        if (token) {
            const claims = decodeToken(token);
            if (claims) {
                try {
                    const response = await fetchWithAuth('/api/user/me');
                    if (response.ok) {
                        const data = await response.json();
                        setPlanStatus(data.plan_status || 'free');
                        setIsAdmin(data.role === 'admin');
                        setLogado(true);
                    } else {
                         handleUnauthorized();
                    }
                } catch (error) {
                    console.error("Erro ao buscar dados do usuário:", error);
                    handleUnauthorized();
                }
            } else {
                handleUnauthorized(); // Token inválido
            }
        } else {
            // Se não há token ao carregar, marca como não logado e para de carregar
             setLogado(false);
             setIsAdmin(false);
             setPlanStatus('free');
        }
        setIsLoadingUser(false);
    }, [handleUnauthorized]);

    useEffect(() => {
        fetchUserData(); // Busca dados ao montar o App
    }, [fetchUserData]); // A dependência agora é a própria função memoizada

    useEffect(() => {
        const handleFocus = () => {
            if (getToken()) {
                fetchUserData();
            }
        };
        window.addEventListener('focus', handleFocus);
        return () => {
            window.removeEventListener('focus', handleFocus);
        };
    }, [fetchUserData]);


    const handleLoginSuccess = () => {
        setLogado(true);
        fetchUserData();
    };

    const handleLogout = () => {
        removeToken();
        setLogado(false);
        setIsAdmin(false);
        setPlanStatus('free');
    };

    const ProtectedRoute = ({ children, adminOnly = false }) => {
        if (isLoadingUser) {
            return <div className="loading-fullscreen">Carregando...</div>;
        }

        if (!logado) {
            return <Navigate to="/login" replace />;
        }
        if (adminOnly && !isAdmin) {
            return <Navigate to="/app" replace />;
        }
        
        const hasActivePlan = ['basic', 'standard', 'premium'].includes(planStatus);
        
        if (isAdmin) {
            return children;
        }

        if (!hasActivePlan) {
            let redirectUrl = "/planos";
            if (planStatus === 'past_due') {
                redirectUrl += "?status=past_due";
            }
            // Evita redirecionar para /planos se já estiver lá ou no success
            const currentPath = window.location.pathname;
            if (currentPath !== '/planos' && currentPath !== '/payment-success') {
                return <Navigate to={redirectUrl} replace />;
            }
        }

        return children;
    };
    
    const PublicRoute = ({ children }) => {
        if (isLoadingUser) {
            return <div className="loading-fullscreen">Carregando...</div>;
        }
        return logado ? <Navigate to="/app" replace /> : children;
    };

    if (isLoadingUser && getToken()) {
         return <div className="loading-fullscreen">Carregando...</div>;
    }

    return (
        // REMOVIDO: <BrowserRouter> daqui
            <Routes>
                {/* --- ROTAS PÚBLICAS (ou que redirecionam se logado) --- */}
                <Route path="/" element={<PublicRoute><LandingPage /></PublicRoute>} />
                <Route path="/login" element={<PublicRoute><Login onLogin={handleLoginSuccess} /></PublicRoute>} />
                <Route path="/cadastro" element={<PublicRoute><Cadastro /></PublicRoute>} />

                {/* --- ROTAS PROTEGIDAS --- */}
                <Route
                    path="/app"
                    element={
                        <ProtectedRoute>
                            <MainApp onLogout={handleLogout} isAdmin={isAdmin} />
                        </ProtectedRoute>
                    }
                />
                <Route
                    path="/admin"
                    element={
                        <ProtectedRoute adminOnly={true}>
                            <AdminDashboard onLogout={handleLogout} />
                        </ProtectedRoute>
                    }
                />
                
                <Route
                    path="/planos"
                    element={
                        logado ? <Planos onLogout={handleLogout} /> : <Navigate to="/login" />
                    }
                />
                
                <Route
                    path="/payment-success"
                    element={
                        logado ? <PaymentSuccess /> : <Navigate to="/login" />
                    }
                 />

                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        // REMOVIDO: </BrowserRouter> daqui
    );
}

export default App;
