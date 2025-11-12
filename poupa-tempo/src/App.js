// /opt/pontua/AutoPonto/poupa-tempo/src/App.js
import React, { useState, useEffect, useCallback } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
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
import './TermsOfServiceModal.css'; // <-- ADICIONADO CSS DOS TERMOS AQUI

// Adicione esta classe de CSS inline ou no seu App.css para o loading
const loadingScreenStyles = {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '100vh',
    width: '100vw',
    backgroundColor: '#1a1a2e', // Fundo escuro
    color: '#e0e6ed',
    fontSize: '1.5rem',
    fontFamily: 'Roboto, sans-serif'
};
const LoadingComponent = () => <div style={loadingScreenStyles}>Carregando...</div>;


function App() {
    const [logado, setLogado] = useState(!!getToken());
    const [isAdmin, setIsAdmin] = useState(false);
    const [planStatus, setPlanStatus] = useState('free');
    const [isLoadingUser, setIsLoadingUser] = useState(true); // Começa true

    const handleUnauthorized = useCallback(() => {
        console.log("Sessão expirada ou inválida. Fazendo logout.");
        removeToken();
        setLogado(false);
        setIsAdmin(false);
        setPlanStatus('free');
        setIsLoadingUser(false);
    }, []);

    // Seta o callback de não autorizado UMA VEZ
    useEffect(() => {
        setUnauthorizedCallback(handleUnauthorized);
    }, [handleUnauthorized]);

    const fetchUserData = useCallback(async () => {
        // Não seta isLoadingUser(true) aqui para evitar re-cargas
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
            // Se não há token, marca como não logado
             setLogado(false);
             setIsAdmin(false);
             setPlanStatus('free');
        }
        setIsLoadingUser(false); // Seta como false ao final
    }, [handleUnauthorized]);

    // Busca dados do usuário apenas uma vez ao carregar o App
    useEffect(() => {
        fetchUserData();
    }, [fetchUserData]); // A dependência agora é a própria função memoizada

    // ***** O useEffect que causava o problema (com 'focus') FOI REMOVIDO *****

    const handleLoginSuccess = () => {
        setIsLoadingUser(true); // Mostra loading ao logar
        setLogado(true);
        fetchUserData();
    };

    const handleLogout = () => {
        removeToken();
        setLogado(false);
        setIsAdmin(false);
        setPlanStatus('free');
    };

    // Componente de Rota Protegida
    const ProtectedRoute = ({ children, adminOnly = false }) => {
        if (isLoadingUser) {
            return <LoadingComponent />;
        }

        if (!logado) {
            return <Navigate to="/login" replace />;
        }
        if (adminOnly && !isAdmin) {
            return <Navigate to="/app" replace />;
        }
        
        const hasActivePlan = ['basic', 'standard', 'premium'].includes(planStatus);
        
        if (isAdmin) {
            return children; // Admin pode acessar tudo
        }

        if (!hasActivePlan) {
            let redirectUrl = "/planos";
            if (planStatus === 'past_due') {
                redirectUrl += "?status=past_due";
            }
            const currentPath = window.location.pathname;
            if (currentPath !== '/planos' && currentPath !== '/payment-success') {
                return <Navigate to={redirectUrl} replace />;
            }
        }

        return children;
    };
    
    // Componente de Rota de Login/Cadastro (redireciona se já logado)
    const PublicRoute = ({ children }) => {
        if (isLoadingUser) {
            return <LoadingComponent />;
        }
        return logado ? <Navigate to="/app" replace /> : children;
    };

    // Loading inicial antes de saber se está logado
    if (isLoadingUser && getToken()) {
         return <LoadingComponent />;
    }

    return (
        // O BrowserRouter está no index.js, então não é necessário aqui
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
    );
}

export default App;
