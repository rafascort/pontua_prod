// src/AdminDashboard.js
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './AdminDashboard.css';
import { fetchWithAuth } from './apiUtils'; // Importa o fetch interceptor
import { isTokenValid } from './authUtils';   // Importa a função de verificação

const AdminDashboard = ({ onLogout }) => {
    const [users, setUsers] = useState([]);
    const [newUserEmail, setNewUserEmail] = useState('');
    const [newUserPassword, setNewUserPassword] = useState('');
    const [newUserRole, setNewUserRole] = useState('user');
    const [error, setError] = useState('');
    const [message, setMessage] = useState('');
    const navigate = useNavigate();

    // Função auxiliar para verificar autenticação antes de ações
    const ensureAuthenticated = () => {
        if (!isTokenValid()) {
            console.warn("Ação administrativa interrompida: Token inválido ou expirado.");
             // Mostra alerta, mas deixa o App.js lidar com o redirecionamento via callback do fetchWithAuth
             setError('A sua sessão expirou ou é inválida. Será redirecionado para o login.');
             // Chama onLogout que foi passado como prop, que por sua vez chama navigate('/login')
             onLogout();
            return false;
        }
        return true;
    };

    const fetchUsers = async () => {
        // Verifica autenticação ANTES da chamada
        if (!ensureAuthenticated()) return;

        setError(''); // Limpa erros anteriores
        try {
            // Usa fetchWithAuth para a requisição GET
            const response = await fetchWithAuth('/api/admin/users');

            if (response.ok) {
                const data = await response.json();
                setUsers(data);
            } else {
                // Trata outros erros HTTP que não sejam 401
                const errorData = await response.json();
                setError(errorData.msg || 'Erro ao carregar usuários.');
            }
        } catch (err) {
            // Se o erro for de autenticação, o onLogout já foi chamado pelo fetchWithAuth
            // Trata outros erros (rede, etc.)
            if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') {
                setError('Erro de rede ao buscar usuários.');
            }
        }
    };

    const handleCreateUser = async (e) => {
        e.preventDefault();
        // Verifica autenticação ANTES da chamada
        if (!ensureAuthenticated()) return;

        setError('');
        setMessage('');

        try {
            // Usa fetchWithAuth para a requisição POST
            const response = await fetchWithAuth('/api/admin/users', {
                method: 'POST',
                // Content-Type será adicionado automaticamente para JSON
                body: JSON.stringify({ email: newUserEmail, password: newUserPassword, role: newUserRole })
            });

            if (response.ok) {
                setMessage('Usuário criado com sucesso!');
                setNewUserEmail('');
                setNewUserPassword('');
                setNewUserRole('user');
                fetchUsers(); // Recarrega a lista de usuários
            } else {
                const errorData = await response.json();
                setError(errorData.msg || 'Erro ao criar usuário.');
            }
        } catch (err) {
            if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') {
                setError('Erro de rede ao criar usuário.');
            }
        }
    };

    const handleToggleUserStatus = async (userId, currentStatus) => {
         // Verifica autenticação ANTES da chamada
         if (!ensureAuthenticated()) return;

        setError('');
        setMessage('');

        try {
             // Usa fetchWithAuth para a requisição PUT
            const response = await fetchWithAuth(`/api/admin/users/${userId}/status`, {
                method: 'PUT',
                body: JSON.stringify({ is_active: !currentStatus })
            });

            if (response.ok) {
                setMessage(`Status do usuário atualizado com sucesso!`);
                fetchUsers(); // Recarrega a lista
            } else {
                const errorData = await response.json();
                setError(errorData.msg || 'Erro ao atualizar status.');
            }
        } catch (err) {
            if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') {
                setError('Erro de rede ao atualizar status.');
            }
        }
    };

    const handleDeleteUser = async (userId, userEmail) => {
        // Verifica autenticação ANTES da confirmação e da chamada
        if (!ensureAuthenticated()) return;

        setError('');
        setMessage('');

        if (!window.confirm(`Tem certeza que deseja excluir o usuário ${userEmail}? Esta ação é irreversível.`)) {
            return;
        }

        try {
            // Usa fetchWithAuth para a requisição DELETE
            const response = await fetchWithAuth(`/api/admin/users/${userId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                setMessage(`Usuário ${userEmail} excluído com sucesso!`);
                fetchUsers(); // Recarrega a lista
            } else {
                const errorData = await response.json();
                setError(errorData.msg || 'Erro ao excluir usuário.');
            }
        } catch (err) {
             if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') {
                setError('Erro de rede ao excluir usuário.');
            }
        }
    };

    const handleResetAllCounts = async () => {
         // Verifica autenticação ANTES da confirmação e da chamada
         if (!ensureAuthenticated()) return;

        setError('');
        setMessage('');

        if (!window.confirm("Tem certeza que deseja zerar a contagem de páginas para TODOS os usuários não-admin? Esta ação não pode ser desfeita.")) {
            return;
        }

        try {
             // Usa fetchWithAuth para a requisição POST
            const response = await fetchWithAuth(`/api/admin/users/reset-pages`, {
                method: 'POST'
            });

            if (response.ok) {
                const data = await response.json();
                setMessage(data.msg || "Contagem de páginas zerada com sucesso!");
                fetchUsers(); // Recarrega a lista
            } else {
                const errorData = await response.json();
                setError(errorData.msg || 'Erro ao zerar a contagem de páginas.');
            }
        } catch (err) {
             if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') {
                setError('Erro de rede ao tentar zerar a contagem.');
            }
        }
    };

    const handleResetUserCount = async (userId, userEmail) => {
        // Verifica autenticação ANTES da confirmação e da chamada
        if (!ensureAuthenticated()) return;

        setError('');
        setMessage('');

        if (!window.confirm(`Tem certeza de que deseja zerar a contagem de páginas para o usuário ${userEmail}?`)) {
            return;
        }

        try {
            // Usa fetchWithAuth para a requisição POST
            const response = await fetchWithAuth(`/api/admin/users/${userId}/reset-pages`, {
                method: 'POST'
            });

            if (response.ok) {
                const data = await response.json();
                setMessage(data.msg || "Contagem do usuário zerada com sucesso!");
                fetchUsers(); // Recarrega a lista
            } else {
                const errorData = await response.json();
                setError(errorData.msg || 'Erro ao zerar contagem do usuário.');
            }
        } catch (err) {
             if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') {
                setError('Erro de rede ao tentar zerar a contagem.');
            }
        }
    };

    // useEffect para buscar usuários na montagem
    useEffect(() => {
        fetchUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []); // Executa apenas na montagem

    // useEffect para limpar mensagens após um tempo
    useEffect(() => {
        let timer;
        if (message || error) {
            timer = setTimeout(() => {
                setMessage('');
                setError('');
            }, 5000); // Limpa após 5 segundos
        }
        return () => clearTimeout(timer); // Limpa o timer se o componente desmontar
    }, [message, error]);


    return (
        <div className="admin-dashboard-container">
            <header className="admin-header">
                <h1>Painel de Administração</h1>
                <div>
                    {/* Botão para voltar para a app principal */}
                    <button onClick={() => navigate('/app')} className="access-system-button">Acessar Sistema</button>
                    {/* Botão de logout manual */}
                    <button onClick={onLogout} className="logout-button">Sair</button>
                </div>
            </header>
            <main className="admin-content">
                {/* Exibe mensagens de erro ou sucesso */}
                {error && <p className="error-message">{error}</p>}
                {message && <p className="success-message">{message}</p>}

                {/* Secção para criar novo usuário */}
                <section className="create-user-section">
                    <h2>Criar Novo Usuário</h2>
                    <form onSubmit={handleCreateUser} className="create-user-form">
                        <input type="email" placeholder="E-mail" value={newUserEmail} onChange={(e) => setNewUserEmail(e.target.value)} required />
                        <input type="password" placeholder="Senha" value={newUserPassword} onChange={(e) => setNewUserPassword(e.target.value)} required />
                        <select value={newUserRole} onChange={(e) => setNewUserRole(e.target.value)}>
                            <option value="user">Usuário Comum</option>
                            <option value="admin">Administrador</option>
                        </select>
                        <button type="submit">Criar Usuário</button>
                    </form>
                </section>

                {/* Secção para gerenciar usuários existentes */}
                <section className="user-list-section">
                     <div className="user-list-header">
                        <h2>Gerenciar Usuários</h2>
                        {/* Botão para zerar contagem de todos os não-admins */}
                        <button onClick={handleResetAllCounts} className="reset-button">
                            Zerar Contagem Geral (não-admins)
                        </button>
                    </div>
                     <div className="table-responsive"> {/* Wrapper para responsividade */}
                         <table className="users-table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>E-mail</th>
                                    <th>Google</th>
                                    <th>Status</th>
                                    <th>Nível</th>
                                    <th>Páginas</th>
                                    <th>Ações</th>
                                </tr>
                            </thead>
                            <tbody>
                                {users.map((user) => (
                                    <tr key={user.id}>
                                        <td data-label="ID">{user.id}</td>
                                        <td data-label="E-mail">{user.email}</td>
                                        <td data-label="Google">{user.google_id ? 'Sim' : 'Não'}</td>
                                        <td data-label="Status">{user.is_active ? 'Ativo' : 'Inativo'}</td>
                                        <td data-label="Nível">{user.role}</td>
                                        <td data-label="Páginas">{user.page_count}</td>
                                        <td data-label="Ações" className="actions-cell">
                                            {/* Botão Ativar/Desativar */}
                                            <button onClick={() => handleToggleUserStatus(user.id, user.is_active)} className={user.is_active ? 'deactivate-button' : 'activate-button'}>
                                                {user.is_active ? 'Desativar' : 'Ativar'}
                                            </button>
                                            {/* Botão Zerar Contagem Individual */}
                                            <button onClick={() => handleResetUserCount(user.id, user.email)} className="reset-user-button" title="Zerar contagem de páginas deste usuário">
                                                Zerar
                                            </button>
                                            {/* Botão Excluir */}
                                            <button onClick={() => handleDeleteUser(user.id, user.email)} className="delete-button">
                                                Excluir
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                                {users.length === 0 && (
                                    <tr>
                                        <td colSpan="7" style={{ textAlign: 'center', color: '#888' }}>Nenhum usuário encontrado.</td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div> {/* Fim .table-responsive */}
                </section>
            </main>
        </div>
    );
};

export default AdminDashboard;
