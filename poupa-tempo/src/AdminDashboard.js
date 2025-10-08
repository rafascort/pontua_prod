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
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (response.status === 401 || response.status === 403) {
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
            setError('Erro de rede ao buscar usuários.');
        }
    };

    const handleCreateUser = async (e) => {
        e.preventDefault();
        setError('');
        setMessage('');
        const token = localStorage.getItem('jwt_token');
        if (!token) return;

        try {
            const response = await fetch('/api/admin/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ email: newUserEmail, password: newUserPassword, role: newUserRole })
            });

            if (response.status === 401 || response.status === 403) { onLogout(); return; }

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
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ is_active: !currentStatus })
            });

            if (response.status === 401 || response.status === 403) { onLogout(); return; }

            if (response.ok) {
                setMessage(`Status do usuário atualizado com sucesso!`);
                fetchUsers();
            } else {
                const errorData = await response.json();
                setError(errorData.msg || 'Erro ao atualizar status.');
            }
        } catch (err) {
            setError('Erro de rede ao atualizar status.');
        }
    };

    const handleDeleteUser = async (userId, userEmail) => {
        setError('');
        setMessage('');
        const token = localStorage.getItem('jwt_token');
        if (!token) return;

        if (!window.confirm(`Tem certeza que deseja excluir o usuário ${userEmail}? Esta ação é irreversível.`)) {
            return;
        }

        try {
            const response = await fetch(`/api/admin/users/${userId}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${token}` }
            });

            if (response.status === 401 || response.status === 403) { onLogout(); return; }

            if (response.ok) {
                setMessage(`Usuário ${userEmail} excluído com sucesso!`);
                fetchUsers();
            } else {
                const errorData = await response.json();
                setError(errorData.msg || 'Erro ao excluir usuário.');
            }
        } catch (err) {
            setError('Erro de rede ao excluir usuário.');
        }
    };
    
    const handleResetAllCounts = async () => {
        setError('');
        setMessage('');
        const token = localStorage.getItem('jwt_token');
        if (!token) return;

        if (!window.confirm("Tem certeza que deseja zerar a contagem de páginas para TODOS os usuários? Esta ação não pode ser desfeita.")) {
            return;
        }

        try {
            const response = await fetch(`/api/admin/users/reset-pages`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            });

            if (response.status === 401 || response.status === 403) { onLogout(); return; }

            if (response.ok) {
                const data = await response.json();
                setMessage(data.msg || "Contagem de páginas zerada com sucesso!");
                fetchUsers();
            } else {
                const errorData = await response.json();
                setError(errorData.msg || 'Erro ao zerar a contagem de páginas.');
            }
        } catch (err) {
            setError('Erro de rede ao tentar zerar a contagem.');
        }
    };

    const handleResetUserCount = async (userId, userEmail) => {
        setError('');
        setMessage('');
        const token = localStorage.getItem('jwt_token');
        if (!token) return;

        if (!window.confirm(`Tem certeza de que deseja zerar a contagem de páginas para o usuário ${userEmail}?`)) {
            return;
        }

        try {
            const response = await fetch(`/api/admin/users/${userId}/reset-pages`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` }
            });

            if (response.status === 401 || response.status === 403) { onLogout(); return; }

            if (response.ok) {
                const data = await response.json();
                setMessage(data.msg || "Contagem do usuário zerada com sucesso!");
                fetchUsers();
            } else {
                const errorData = await response.json();
                setError(errorData.msg || 'Erro ao zerar contagem do usuário.');
            }
        } catch (err) {
            setError('Erro de rede ao tentar zerar a contagem.');
        }
    };
    
    useEffect(() => {
        fetchUsers();
    }, []);
    
    useEffect(() => {
        if (message || error) {
            const timer = setTimeout(() => { setMessage(''); setError(''); }, 5000);
            return () => clearTimeout(timer);
        }
    }, [message, error]);

    return (
        <div className="admin-dashboard-container">
            <header className="admin-header">
                <h1>Painel de Administração</h1>
                <div>
                    <button onClick={() => navigate('/app')} className="access-system-button">Acessar Sistema</button>
                    <button onClick={onLogout} className="logout-button">Sair</button>
                </div>
            </header>
            <main className="admin-content">
                {error && <p className="error-message">{error}</p>}
                {message && <p className="success-message">{message}</p>}

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

                <section className="user-list-section">
                     <div className="user-list-header">
                        <h2>Gerenciar Usuários</h2>
                        <button onClick={handleResetAllCounts} className="reset-button">
                            Zerar Contagem de Páginas
                        </button>
                    </div>
                     <table className="users-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>E-mail</th>
                                <th>Google ID</th>
                                <th>Status</th>
                                <th>Nível</th>
                                <th>Páginas Usadas</th>
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
                                    <td>{user.page_count}</td>
                                    <td className="actions-cell">
                                        <button onClick={() => handleToggleUserStatus(user.id, user.is_active)} className={user.is_active ? 'deactivate-button' : 'activate-button'}>
                                            {user.is_active ? 'Desativar' : 'Ativar'}
                                        </button>
                                        <button onClick={() => handleResetUserCount(user.id, user.email)} className="reset-user-button">
                                            Zerar
                                        </button>
                                        <button onClick={() => handleDeleteUser(user.id, user.email)} className="delete-button">
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
