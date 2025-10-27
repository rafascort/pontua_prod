// /opt/pontua/AutoPonto/poupa-tempo/src/AdminDashboard.js
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import './AdminDashboard.css';
import { fetchWithAuth } from './apiUtils';
// --- CORREÇÃO AQUI: Adicionado getToken e decodeToken ---
import { isTokenValid, getToken, decodeToken } from './authUtils';
import PasswordResetModal from './PasswordResetModal';
import UserEditModal from './UserEditModal';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faPencilAlt } from '@fortawesome/free-solid-svg-icons';

const AdminDashboard = ({ onLogout }) => {
    const [users, setUsers] = useState([]);
    const [error, setError] = useState('');
    const [message, setMessage] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);
    const [search, setSearch] = useState('');
    const [userToResetPassword, setUserToResetPassword] = useState(null);
    const [isResettingPassword, setIsResettingPassword] = useState(false);
    const [userToEdit, setUserToEdit] = useState(null);
    const [isEditingUser, setIsEditingUser] = useState(false);
    const [sortField, setSortField] = useState('id');
    const [sortOrder, setSortOrder] = useState('asc');
    const [filterPlan, setFilterPlan] = useState('all');

    const navigate = useNavigate();

    const ensureAuthenticated = useCallback(() => {
        if (!isTokenValid()) {
            console.warn("Ação administrativa interrompida: Token inválido ou expirado.");
            setError('A sua sessão expirou ou é inválida. Será redirecionado para o login.');
            setTimeout(onLogout, 1500);
            return false;
        }
        return true;
    }, [onLogout]);

    const fetchUsers = useCallback(async (
        currentPage = 1,
        currentSearch = '',
        currentSortField = 'id',
        currentSortOrder = 'asc',
        currentFilterPlan = 'all'
    ) => {
        if (!ensureAuthenticated()) return;

        setIsLoading(true);
        try {
            const queryParams = new URLSearchParams({
                page: currentPage,
                per_page: 10,
                search: currentSearch,
                sort_by: currentSortField,
                sort_order: currentSortOrder,
                filter_plan: currentFilterPlan,
            });
            const response = await fetchWithAuth(`/api/admin/users?${queryParams.toString()}`);

            if (response.ok) {
                const data = await response.json();
                setUsers(data.users || []);
                setTotalPages(data.total_pages || 1);
                setPage(data.current_page || 1);
            } else {
                const errorData = await response.json();
                setError(errorData.msg || 'Erro ao carregar usuários.');
                setUsers([]);
            }
        } catch (err) {
            if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') {
                setError('Erro de rede ao buscar usuários.');
                setUsers([]);
            }
        } finally {
            setIsLoading(false);
        }
    }, [ensureAuthenticated]);

    const handleSort = (field) => {
        const newOrder = (field === sortField && sortOrder === 'asc') ? 'desc' : 'asc';
        setSortField(field);
        setSortOrder(newOrder);
    };

    const handleFilterPlanChange = (e) => {
        const newPlanFilter = e.target.value;
        setFilterPlan(newPlanFilter);
    };

    const handleSearchChange = (e) => {
        setSearch(e.target.value);
    };

    const handleSearchSubmit = (e) => {
        e.preventDefault();
        setPage(1); // Reseta para a página 1 ao buscar
        fetchUsers(1, search, sortField, sortOrder, filterPlan);
    };

    const handlePageChange = (newPage) => {
        if (newPage >= 1 && newPage <= totalPages && newPage !== page) {
             setPage(newPage);
        }
    };

    // useEffect para buscar usuários
    useEffect(() => {
        fetchUsers(page, search, sortField, sortOrder, filterPlan);
    }, [fetchUsers, page, sortField, sortOrder, filterPlan, search]); // 'search' adicionado aqui

    // Limpar mensagens
    useEffect(() => {
        let timer;
        if (message || error) { timer = setTimeout(() => { setMessage(''); setError(''); }, 5000); }
        return () => clearTimeout(timer);
    }, [message, error]);

    // --- Ações de Botão ---

    const handleToggleUserStatus = async (userId, currentStatus) => {
        if (!ensureAuthenticated()) return;
        setError(''); setMessage('');
        try {
           const response = await fetchWithAuth(`/api/admin/users/${userId}/status`, {
               method: 'PUT',
               body: JSON.stringify({ is_active: !currentStatus })
           });
           if (response.ok) {
               setMessage(`Status atualizado!`);
               fetchUsers(page, search, sortField, sortOrder, filterPlan);
           } else { const d = await response.json(); setError(d.msg || 'Erro.'); }
        } catch (err) { if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') { setError('Erro de rede.'); } }
    };

    const handleDeleteUser = async (userId, userEmail) => {
        if (!ensureAuthenticated()) return;
        setError(''); setMessage('');
        if (!window.confirm(`Tem certeza que deseja excluir o usuário ${userEmail}? Esta ação é irreversível.`)) return;
        try {
            const response = await fetchWithAuth(`/api/admin/users/${userId}`, { method: 'DELETE' });
            if (response.ok) {
                setMessage(`Usuário ${userEmail} excluído!`);
                const newPage = (users.length === 1 && page > 1) ? page - 1 : page;
                setPage(newPage); // Atualiza o estado da página antes de recarregar
                fetchUsers(newPage, search, sortField, sortOrder, filterPlan);
            } else { const d = await response.json(); setError(d.msg || 'Erro.'); }
        } catch (err) { if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') { setError('Erro de rede.'); } }
    };

     const handleResetAllCounts = async () => {
         if (!ensureAuthenticated()) return;
         setError(''); setMessage('');
         if (!window.confirm("Tem certeza que deseja zerar a contagem de páginas de TODOS os usuários não-admins?")) return;
         try {
             const response = await fetchWithAuth(`/api/admin/users/reset-pages`, { method: 'POST' });
             if (response.ok) { const d = await response.json(); setMessage(d.msg || "OK!"); fetchUsers(page, search, sortField, sortOrder, filterPlan); }
             else { const d = await response.json(); setError(d.msg || 'Erro.'); }
         } catch (err) { if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') { setError('Erro de rede.'); } }
     };

     const handleResetUserCount = async (userId, userEmail) => {
         if (!ensureAuthenticated()) return;
         setError(''); setMessage('');
         if (!window.confirm(`Tem certeza que deseja zerar a contagem de páginas para ${userEmail}?`)) return;
         try {
             const response = await fetchWithAuth(`/api/admin/users/${userId}/reset-pages`, { method: 'POST' });
             if (response.ok) { const d = await response.json(); setMessage(d.msg || "OK!"); fetchUsers(page, search, sortField, sortOrder, filterPlan); }
             else { const d = await response.json(); setError(d.msg || 'Erro.'); }
         } catch (err) { if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') { setError('Erro de rede.'); } }
     };

    // --- Funções do Modal de Senha ---
    const openPasswordResetModal = (user) => setUserToResetPassword(user);
    const closePasswordResetModal = () => { setUserToResetPassword(null); setIsResettingPassword(false); };
    const handleConfirmPasswordReset = async (newPassword) => {
       if (!userToResetPassword || !ensureAuthenticated()) return;
       setIsResettingPassword(true); setError(''); setMessage('');
       try {
           const response = await fetchWithAuth(`/api/admin/users/${userToResetPassword.id}`, {
               method: 'PUT', body: JSON.stringify({ new_password: newPassword })
           });
           if (response.ok) {
               setMessage(`Senha para ${userToResetPassword.email} resetada!`);
               closePasswordResetModal();
           } else {
               const errorData = await response.json();
               // Mostra o erro dentro do modal de senha
               setUserToResetPassword(prev => ({...prev, error: errorData.msg || 'Erro desconhecido.'}));
           }
       } catch (err) {
            if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') {
               setError('Erro de rede ao resetar senha.');
            }
       } finally { setIsResettingPassword(false); }
    };

    // --- Funções para o Modal de Edição ---
    const openUserEditModal = (user) => {
        setUserToEdit(user);
        setIsEditingUser(false);
    };
    const closeUserEditModal = () => {
        setUserToEdit(null);
        setIsEditingUser(false);
    };
    const handleConfirmUserEdit = async (userId, updates) => {
        if (!userToEdit || !ensureAuthenticated()) return;
        setIsEditingUser(true); setError(''); setMessage('');

        try {
            const response = await fetchWithAuth(`/api/admin/users/${userId}`, {
                method: 'PUT',
                body: JSON.stringify(updates)
            });

            if (response.ok) {
                 const data = await response.json();
                 setMessage(data.msg || "Usuário atualizado!");
                 closeUserEditModal();
                 fetchUsers(page, search, sortField, sortOrder, filterPlan);
            } else {
                 const errorData = await response.json();
                 // Mostra o erro dentro do modal de edição
                 setUserToEdit(prev => ({...prev, error: errorData.msg || 'Erro ao salvar.'}));
            }
        } catch (err) {
             if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') {
                setError('Erro de rede ao salvar usuário.');
             }
        } finally {
            setIsEditingUser(false);
        }
    };

    // Pega o e-mail do admin logado para desabilitar botões
    const token = getToken(); // Usa a função importada
    const decodedToken = decodeToken(token); // Usa a função importada
    const loggedInAdminEmail = decodedToken?.sub;

    const getSortIcon = (field) => {
        if (field !== sortField) return <span className="sort-icon">↕</span>;
        return sortOrder === 'asc' ? <span className="sort-icon">▲</span> : <span className="sort-icon">▼</span>;
    };


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

                <section className="user-list-section">
                    <div className="user-list-header">
                        <h2>Gerenciar Usuários</h2>
                        <button onClick={handleResetAllCounts} className="reset-button">
                            Zerar Contagem Geral (não-admins)
                        </button>
                    </div>

                    <div className="filter-search-area">
                         <div className="filter-group">
                             <label htmlFor="planFilter">Filtrar por Plano:</label>
                             <select id="planFilter" value={filterPlan} onChange={handleFilterPlanChange}>
                                 <option value="all">Todos</option>
                                 <option value="free">Free</option>
                                 <option value="basic">Básico</option>
                                 <option value="standard">Padrão</option>
                                 <option value="premium">Premium</option>
                                 <option value="past_due">Pagamento Pendente</option>
                             </select>
                         </div>
                        <form onSubmit={handleSearchSubmit} className="search-form">
                             <label htmlFor="searchEmail">Buscar por Email:</label>
                             <input
                                id="searchEmail"
                                type="text"
                                placeholder="Digite o email..."
                                value={search}
                                onChange={handleSearchChange}
                             />
                             <button type="submit">Buscar</button>
                        </form>
                    </div>

                    <div className="table-responsive">
                        <table className="users-table">
                            <thead>
                                <tr>
                                    <th onClick={() => handleSort('id')} className={sortField === 'id' ? `sort-${sortOrder}` : ''}>
                                        ID {getSortIcon('id')}
                                    </th>
                                    <th onClick={() => handleSort('email')} className={sortField === 'email' ? `sort-${sortOrder}` : ''}>
                                        E-mail {getSortIcon('email')}
                                    </th>
                                    <th onClick={() => handleSort('status')} className={sortField === 'status' ? `sort-${sortOrder}` : ''}>
                                        Status {getSortIcon('status')}
                                    </th>
                                    <th onClick={() => handleSort('role')} className={sortField === 'role' ? `sort-${sortOrder}` : ''}>
                                        Nível {getSortIcon('role')}
                                    </th>
                                    <th onClick={() => handleSort('plan')} className={sortField === 'plan' ? `sort-${sortOrder}` : ''}>
                                        Plano {getSortIcon('plan')}
                                    </th>
                                    <th onClick={() => handleSort('pages')} className={sortField === 'pages' ? `sort-${sortOrder}` : ''}>
                                        Páginas {getSortIcon('pages')}
                                    </th>
                                    <th>Ações</th>
                                </tr>
                            </thead>
                            <tbody>
                                {isLoading ? (
                                    <tr><td colSpan="7" style={{ textAlign: 'center' }}>Carregando...</td></tr>
                                ) : users.length > 0 ? (
                                    users.map((user) => (
                                        <tr key={user.id}>
                                            <td data-label="ID">{user.id}</td>
                                            <td data-label="E-mail" className="email-cell">{user.email}</td>
                                            <td data-label="Status">{user.is_active ? 'Ativo' : 'Inativo'}</td>
                                            <td data-label="Nível">{user.role}</td>
                                            <td data-label="Plano">{user.plan_status || 'free'}</td>
                                            <td data-label="Páginas">{user.page_count}</td>
                                            <td data-label="Ações" className="actions-cell">
                                                <button
                                                    onClick={() => openUserEditModal(user)}
                                                    className="edit-button"
                                                    title="Editar dados do usuário">
                                                    <FontAwesomeIcon icon={faPencilAlt} /> Editar
                                                </button>
                                                <button
                                                    onClick={() => handleToggleUserStatus(user.id, user.is_active)}
                                                    className={user.is_active ? 'deactivate-button' : 'activate-button'}
                                                    disabled={user.email === loggedInAdminEmail}
                                                    title={user.email === loggedInAdminEmail ? "Não pode alterar seu próprio status" : (user.is_active ? "Desativar usuário" : "Ativar usuário")}
                                                >
                                                    {user.is_active ? 'Desativar' : 'Ativar'}
                                                </button>
                                                 <button
                                                    onClick={() => openPasswordResetModal(user)}
                                                    className="reset-user-button"
                                                    title="Resetar senha deste usuário">
                                                    Senha
                                                 </button>
                                                <button
                                                    onClick={() => handleResetUserCount(user.id, user.email)}
                                                    className="reset-user-button"
                                                    title="Zerar contagem de páginas">
                                                    Zerar
                                                </button>
                                                <button
                                                    onClick={() => handleDeleteUser(user.id, user.email)}
                                                    className="delete-button"
                                                    disabled={user.email === loggedInAdminEmail}
                                                    title={user.email === loggedInAdminEmail ? "Não pode excluir sua própria conta" : "Excluir usuário"}
                                                >
                                                    Excluir
                                                </button>
                                            </td>
                                        </tr>
                                    ))
                                ) : (
                                    <tr><td colSpan="7" style={{ textAlign: 'center' }}>Nenhum usuário encontrado.</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                    
                    {!isLoading && totalPages > 1 && (
                        <div className="pagination">
                            <button onClick={() => handlePageChange(page - 1)} disabled={page <= 1}>
                                Anterior
                            </button>
                            <span>Página {page} de {totalPages}</span>
                            <button onClick={() => handlePageChange(page + 1)} disabled={page >= totalPages}>
                                Próxima
                            </button>
                        </div>
                    )}
                </section>
            </main>

             {userToResetPassword && (
                 <PasswordResetModal
                    userEmail={userToResetPassword.email}
                    onConfirm={handleConfirmPasswordReset}
                    onCancel={closePasswordResetModal}
                    isLoading={isResettingPassword}
                    // Passa o erro para o modal se houver
                    apiError={userToResetPassword.error}
                 />
             )}

            {userToEdit && (
                <UserEditModal
                    user={userToEdit}
                    onConfirm={handleConfirmUserEdit}
                    onCancel={closeUserEditModal}
                    isLoading={isEditingUser}
                     // Passa o erro para o modal se houver
                    apiError={userToEdit.error}
                />
            )}
        </div>
    );
};

export default AdminDashboard;
