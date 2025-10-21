// /opt/pontua/AutoPonto/poupa-tempo/src/App.js
import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import Login from './Login';
import MainApp from './MainApp';
import AdminDashboard from './AdminDashboard';
import './App.css';
import useRemoveNBSP from './hooks/useRemoveNBSP';
import { isTokenValid, decodeToken } from './authUtils'; // Importa ambas do novo ficheiro
import { setUnauthorizedCallback } from './apiUtils'; // Importa a configuração do interceptor

function App() {
    useRemoveNBSP();
    const [logado, setLogado] = useState(false); // Estado inicial é deslogado
    const [isAdmin, setIsAdmin] = useState(false);
    const navigate = useNavigate();
    const location = useLocation(); // Para ler parâmetros da URL

    // Função de tratamento para quando o token é inválido ou expirado
    const handleUnauthorized = () => {
        // Evita chamadas múltiplas se já estiver deslogando
        if (!logado && location.pathname === '/login') return;

        console.log("Executando handleUnauthorized (logout forçado)");
        localStorage.removeItem('jwt_token');
        setLogado(false);
        setIsAdmin(false);
        // Redireciona para login com uma flag indicando que a sessão expirou
        navigate('/login?sessionExpired=true', { replace: true });
    };

    useEffect(() => {
        // Configura o callback global para tratar 401 detectado pelo fetchWithAuth
        setUnauthorizedCallback(handleUnauthorized);

        // Verifica o estado inicial do login ao carregar a aplicação
        if (isTokenValid()) {
            const token = localStorage.getItem('jwt_token');
            const decoded = decodeToken(token); // Re-decodifica para pegar o role
            setLogado(true);
            setIsAdmin(decoded?.role === 'admin');
        } else {
            // Se o token não for válido no carregamento inicial, garante que o estado esteja deslogado
            // E se não estivermos já na página de login, força o redirecionamento
            if (location.pathname !== '/login') {
                handleUnauthorized();
            } else {
                 setLogado(false);
                 setIsAdmin(false);
            }
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []); // Executa apenas uma vez na montagem inicial

    // Chamado pelo componente Login após sucesso
    const handleLoginSuccess = () => {
        if (isTokenValid()) {
            const token = localStorage.getItem('jwt_token');
            const decoded = decodeToken(token);
            setLogado(true);
            setIsAdmin(decoded?.role === 'admin');
            // A navegação agora é feita dentro do Login.js baseado no token decodificado
        } else {
             // Caso algo estranho ocorra logo após o login
             handleUnauthorized();
        }
    };

     // Chamado pelo botão Sair ou outras ações manuais de logout
     const handleLogout = () => {
        console.log("Executando handleLogout (manual)");
        localStorage.removeItem('jwt_token');
        setLogado(false);
        setIsAdmin(false);
        navigate('/login', { replace: true });
    };

    // Componente wrapper para rotas protegidas
    const ProtectedRoute = ({ children, requireAdmin = false }) => {
        if (!logado) {
            // Se não estiver logado, redireciona para login
            return <Navigate to="/login?redirected=true" replace />;
        }
        if (requireAdmin && !isAdmin) {
             // Se requer admin mas não é admin, redireciona para a app principal (ou login)
             console.warn("Tentativa de acesso não autorizado à rota de admin.");
             return <Navigate to="/app" replace />; // Ou para /login se preferir
        }
        // Se logado (e admin, se necessário), renderiza o componente filho
        return children;
    };


    return (
        <Routes>
            {/* Passa a função onLogin para o componente Login */}
            <Route path="/login" element={<Login onLogin={handleLoginSuccess} />} />

            {/* Rota para a aplicação principal */}
            <Route
                path="/app"
                element={
                    <ProtectedRoute>
                        <MainApp onLogout={handleLogout} isAdmin={isAdmin} />
                    </ProtectedRoute>
                }
            />

            {/* Rota para o painel de administração */}
            <Route
                path="/admin"
                element={
                    <ProtectedRoute requireAdmin={true}>
                        <AdminDashboard onLogout={handleLogout} />
                    </ProtectedRoute>
                }
            />

            {/* Redireciona qualquer outra rota para /app se logado, senão para /login */}
            <Route path="*" element={<Navigate to={logado ? "/app" : "/login"} replace />} />
        </Routes>
    );
}

export default App;
