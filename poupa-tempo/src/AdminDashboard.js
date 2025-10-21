// /opt/pontua/AutoPonto/poupa-tempo/src/AdminDashboard.js
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import './AdminDashboard.css';
import { fetchWithAuth } from './apiUtils';
import { isTokenValid, decodeToken } from './authUtils';
import PasswordResetModal from './PasswordResetModal';

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

    // --- NOVOS ESTADOS PARA SORT/FILTER ---
    const [sortField, setSortField] = useState('id'); // Default sort field
    const [sortOrder, setSortOrder] = useState('asc');  // Default sort order
    const [filterPlan, setFilterPlan] = useState('all'); // Default filter ('all', 'free', 'basic', etc.)
    // --- FIM NOVOS ESTADOS ---

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

    // --- fetchUsers ATUALIZADO ---
    const fetchUsers = useCallback(async (
        currentPage = 1,
        currentSearch = '',
        currentSortField = 'id',
        currentSortOrder = 'asc',
        currentFilterPlan = 'all'
    ) => {
        if (!ensureAuthenticated()) return;

        setIsLoading(true);
        setError('');
        try {
            const queryParams = new URLSearchParams({
                page: currentPage,
                per_page: 10,
                search: currentSearch,
                sort_by: currentSortField,
                sort_order: currentSortOrder,
                filter_plan: currentFilterPlan, // Adiciona filtro de plano
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
    }, [ensureAuthenticated]); // Só depende de ensureAuthenticated agora

    // Handler para clique no header da tabela (sorting)
    const handleSort = (field) => {
        const newOrder = (field === sortField && sortOrder === 'asc') ? 'desc' : 'asc';
        setSortField(field);
        setSortOrder(newOrder);
        // Chama fetchUsers com os novos parâmetros de ordenação, resetando para a página 1
        fetchUsers(1, search, field, newOrder, filterPlan);
    };

    // Handler para mudança no filtro de plano
    const handleFilterPlanChange = (e) => {
        const newPlanFilter = e.target.value;
        setFilterPlan(newPlanFilter);
        // Chama fetchUsers com o novo filtro, resetando para a página 1
        fetchUsers(1, search, sortField, sortOrder, newPlanFilter);
    };

    const handleSearchChange = (e) => {
        setSearch(e.target.value);
    };

    // Handler para submit da busca (apenas dispara o fetch com o estado atual)
    const handleSearchSubmit = (e) => {
        e.preventDefault();
        fetchUsers(1, search, sortField, sortOrder, filterPlan); // Busca na página 1
    };

    // Handler para mudança de página
    const handlePageChange = (newPage) => {
        if (newPage >= 1 && newPage <= totalPages && newPage !== page) {
             setPage(newPage); // Atualiza o estado da página
             // FetchUsers será chamado pelo useEffect abaixo
        }
    };


    // useEffect para buscar usuários na montagem E quando filtros/ordenação/página mudam
    useEffect(() => {
        fetchUsers(page, search, sortField, sortOrder, filterPlan);
    // IMPORTANTE: Inclua todas as dependências que disparam o fetch
    }, [fetchUsers, page, sortField, sortOrder, filterPlan, search]);


    // Limpar mensagens (igual antes)
    useEffect(() => {
        let timer;
        if (message || error) { timer = setTimeout(() => { setMessage(''); setError(''); }, 5000); }
        return () => clearTimeout(timer);
    }, [message, error]);

    // Funções de ação (handleToggleUserStatus, etc.) - Chamam fetchUsers com estado atual
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
               fetchUsers(page, search, sortField, sortOrder, filterPlan); // Recarrega com filtros atuais
           } else { const d = await response.json(); setError(d.msg || 'Erro.'); }
        } catch (err) { if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') { setError('Erro de rede.'); } }
    };

    const handleDeleteUser = async (userId, userEmail) => {
        if (!ensureAuthenticated()) return;
        setError(''); setMessage('');
        if (!window.confirm(`Excluir ${userEmail}?`)) return;
        try {
            const response = await fetchWithAuth(`/api/admin/users/${userId}`, { method: 'DELETE' });
            if (response.ok) {
                setMessage(`Usuário ${userEmail} excluído!`);
                // Volta para página 1 se for a última página e só tiver 1 user nela
                const newPage = (users.length === 1 && page > 1) ? page - 1 : page;
                fetchUsers(newPage, search, sortField, sortOrder, filterPlan);
            } else { const d = await response.json(); setError(d.msg || 'Erro.'); }
        } catch (err) { if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') { setError('Erro de rede.'); } }
    };

     const handleResetAllCounts = async () => {
         if (!ensureAuthenticated()) return;
         setError(''); setMessage('');
         if (!window.confirm("Zerar contagem geral (não-admins)?")) return;
         try {
             const response = await fetchWithAuth(`/api/admin/users/reset-pages`, { method: 'POST' });
             if (response.ok) { const d = await response.json(); setMessage(d.msg || "OK!"); fetchUsers(page, search, sortField, sortOrder, filterPlan); }
             else { const d = await response.json(); setError(d.msg || 'Erro.'); }
         } catch (err) { if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') { setError('Erro de rede.'); } }
     };

     const handleResetUserCount = async (userId, userEmail) => {
         if (!ensureAuthenticated()) return;
         setError(''); setMessage('');
         if (!window.confirm(`Zerar contagem para ${userEmail}?`)) return;
         try {
             const response = await fetchWithAuth(`/api/admin/users/${userId}/reset-pages`, { method: 'POST' });
             if (response.ok) { const d = await response.json(); setMessage(d.msg || "OK!"); fetchUsers(page, search, sortField, sortOrder, filterPlan); }
             else { const d = await response.json(); setError(d.msg || 'Erro.'); }
         } catch (err) { if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') { setError('Erro de rede.'); } }
     };

    // Funções do Modal (iguais antes)
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
               alert(`Erro: ${errorData.msg || 'Erro desconhecido.'}`);
               setError(errorData.msg || 'Erro ao resetar senha.');
           }
       } catch (err) {
            if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') {
               setError('Erro de rede ao resetar senha.');
           }
       } finally { setIsResettingPassword(false); }
    };


    // Email do admin logado (igual antes)
    const token = localStorage.getItem('jwt_token');
    const decodedToken = decodeToken(token);
    const loggedInAdminEmail = decodedToken?.email;

    // Helper para ícone de ordenação
    const getSortIcon = (field) => {
        if (field !== sortField) return <span className="sort-icon">↕</span>; // Ícone padrão
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

                     {/* --- ÁREA DE FILTRO E BUSCA --- */}
                    <div className="filter-search-area">
                         <div className="filter-group">
                             <label htmlFor="planFilter">Filtrar por Plano:</label>
                             <select id="planFilter" value={filterPlan} onChange={handleFilterPlanChange}>
                                 <option value="all">Todos</option>
                                 <option value="free">Free</option>
                                 <option value="basic">Básico</option>
                                 <option value="standard">Padrão</option>
                                 <option value="premium">Premium</option>
                                 {/* Adicione outros status de plano se houver */}
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
                     {/* --- FIM ÁREA DE FILTRO E BUSCA --- */}

                    <div className="table-responsive">
                        <table className="users-table">
                            <thead>
                                <tr>
                                    {/* Cabeçalhos clicáveis para ordenar */}
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
                                            <td data-label="E-mail">{user.email}</td>
                                            <td data-label="Status">{user.is_active ? 'Ativo' : 'Inativo'}</td>
                                            <td data-label="Nível">{user.role}</td>
                                            <td data-label="Plano">{user.plan_status || 'free'}</td>
                                            <td data-label="Páginas">{user.page_count}</td>
                                            <td data-label="Ações" className="actions-cell">
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
                    {/* Paginação */}
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
                 />
             )}
        </div>
    );
};

export default AdminDashboard;
