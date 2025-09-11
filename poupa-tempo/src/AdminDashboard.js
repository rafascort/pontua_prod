// src/AdminDashboard.js
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './AdminDashboard.css';

const AdminDashboard = ({ onLogout }) => {
    const [users, setUsers] = useState([]);
    const [newUserEmail, setNewUserEmail] = useState('');
    const [newUserPassword, setNewUserPassword] = useState('');
    const [newUserRole, setNewUserRole] = useState('user');
    const [error, setError] = useState('');
    const [message, setMessage] = useState('');
    const navigate = useNavigate();

    const fetchUsers = async () => {
        setError('');
        const token = localStorage.getItem('jwt_token');
        if (!token) {
            onLogout();
            return;
        }
        try {
            const response = await fetch('/api/admin/users', {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (response.status === 401 || response.status === 403) {
                const errorData = await response.json();
                setError(errorData.msg || 'Você não tem permissão para acessar esta página ou sua sessão expirou.');
                onLogout();
                return;
            }

            if (response.ok) {
                const data = await response.json();
                setUsers(data);
            } else {
                const errorData = await response.json();
                setError(errorData.msg || 'Erro ao carregar usuários.');
            }
        } catch (err) {
            console.error('Erro ao buscar usuários:', err);
            setError('Erro de rede ao buscar usuários.');
        }
    };

    useEffect(() => {
        fetchUsers();
        const timer = setTimeout(() => {
            setMessage('');
            setError('');
        }, 5000);
        return () => clearTimeout(timer);
    }, [message, error]);

    const handleCreateUser = async (e) => {
        e.preventDefault();
        setError('');
        setMessage('');
        const token = localStorage.getItem('jwt_token');
        if (!token) return;

        try {
            const response = await fetch('/api/admin/users', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({
                    email: newUserEmail,
                    password: newUserPassword,
                    role: newUserRole
                })
            });

            if (response.status === 401 || response.status === 403) {
                const errorData = await response.json();
                setError(errorData.msg || 'Você não tem permissão para criar usuários ou sua sessão expirou.');
                onLogout();
                return;
            }

            if (response.ok) {
                setMessage('Usuário criado com sucesso!');
                setNewUserEmail('');
                setNewUserPassword('');
                setNewUserRole('user');
                fetchUsers();
            } else {
                const errorData = await response.json();
                setError(errorData.msg || 'Erro ao criar usuário.');
            }
        } catch (err) {
            console.error('Erro ao criar usuário:', err);
            setError('Erro de rede ao criar usuário.');
        }
    };

    const handleToggleUserStatus = async (userId, currentStatus) => {
        setError('');
        setMessage('');
        const token = localStorage.getItem('jwt_token');
        if (!token) return;

        try {
            const response = await fetch(`/api/admin/users/${userId}/status`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify({ is_active: !currentStatus })
            });

            if (response.status === 401 || response.status === 403) {
                const errorData = await response.json();
                setError(errorData.msg || 'Você não tem permissão para alterar o status do usuário ou sua sessão expirou.');
                onLogout();
                return;
            }

            if (response.ok) {
                setMessage(`Status do usuário atualizado com sucesso!`);
                fetchUsers();
            } else {
                const errorData = await response.json();
                setError(errorData.msg || 'Erro ao atualizar status.');
            }
        } catch (err) {
            console.error('Erro ao atualizar status:', err);
            setError('Erro de rede ao atualizar status.');
        }
    };

    // NOVA FUNÇÃO: Excluir Usuário
    const handleDeleteUser = async (userId, userEmail) => {
        setError('');
        setMessage('');
        const token = localStorage.getItem('jwt_token');
        if (!token) return;

        if (!window.confirm(`Tem certeza que deseja excluir o usuário ${userEmail}? Esta ação é irreversível.`)) {
            return; // Cancela se o usuário não confirmar
        }

        try {
            const response = await fetch(`/api/admin/users/${userId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (response.status === 401 || response.status === 403) {
                const errorData = await response.json();
                setError(errorData.msg || 'Você não tem permissão para excluir usuários ou sua sessão expirou.');
                onLogout();
                return;
            }

            if (response.ok) {
                setMessage(`Usuário ${userEmail} excluído com sucesso!`);
                fetchUsers(); // Recarrega a lista de usuários
            } else {
                const errorData = await response.json();
                setError(errorData.msg || 'Erro ao excluir usuário.');
            }
        } catch (err) {
            console.error('Erro ao excluir usuário:', err);
            setError('Erro de rede ao excluir usuário.');
        }
    };


    return (
        <div className="admin-dashboard-container">
            <header className="admin-header">
                <h1>Painel de Administração</h1>
                <button onClick={onLogout} className="logout-button">Sair</button>
            </header>
            <main className="admin-content">
                {error && <p className="error-message">{error}</p>}
                {message && <p className="success-message">{message}</p>}

                <section className="create-user-section">
                    <h2>Criar Novo Usuário</h2>
                    <form onSubmit={handleCreateUser} className="create-user-form">
                        <input
                            type="email"
                            placeholder="E-mail"
                            value={newUserEmail}
                            onChange={(e) => setNewUserEmail(e.target.value)}
                            required
                        />
                        <input
                            type="password"
                            placeholder="Senha"
                            value={newUserPassword}
                            onChange={(e) => setNewUserPassword(e.target.value)}
                            required
                        />
                        <select value={newUserRole} onChange={(e) => setNewUserRole(e.target.value)}>
                            <option value="user">Usuário Comum</option>
                            <option value="admin">Administrador</option>
                        </select>
                        <button type="submit">Criar Usuário</button>
                    </form>
                </section>

                <section className="user-list-section">
                    <h2>Gerenciar Usuários</h2>
                    <table className="users-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>E-mail</th>
                                <th>Google ID</th>
                                <th>Status</th>
                                <th>Nível</th>
                                <th>Ações</th>
                            </tr>
                        </thead>
                        <tbody>
                            {users.map((user) => (
                                <tr key={user.id}>
                                    <td>{user.id}</td>
                                    <td>{user.email}</td>
                                    <td>{user.google_id ? 'Sim' : 'Não'}</td>
                                    <td>{user.is_active ? 'Ativo' : 'Inativo'}</td>
                                    <td>{user.role}</td>
                                    <td>
                                        <button
                                            onClick={() => handleToggleUserStatus(user.id, user.is_active)}
                                            className={user.is_active ? 'deactivate-button' : 'activate-button'}
                                            disabled={user.role === 'admin' && user.email === 'admin@sistemaponto.com'}
                                        >
                                            {user.is_active ? 'Desativar' : 'Ativar'}
                                        </button>
                                        {/* NOVO BOTÃO: Excluir */}
                                        <button
                                            onClick={() => handleDeleteUser(user.id, user.email)}
                                            className="delete-button"
                                            style={{ marginLeft: '10px', backgroundColor: '#dc3545', color: 'white' }}
                                            disabled={user.role === 'admin' && user.email === 'admin@sistemaponto.com'}
                                        >
                                            Excluir
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </section>
            </main>
        </div>
    );
};

export default AdminDashboard;

