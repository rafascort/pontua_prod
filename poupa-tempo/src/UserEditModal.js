// /opt/pontua/AutoPonto/poupa-tempo/src/UserEditModal.js
import React, { useState, useEffect } from 'react';
import './UserEditModal.css'; // Criaremos este CSS

const UserEditModal = ({ user, onConfirm, onCancel, isLoading }) => {
    const [email, setEmail] = useState('');
    const [role, setRole] = useState('user');
    const [planStatus, setPlanStatus] = useState('free');
    const [pageCount, setPageCount] = useState(0);
    const [error, setError] = useState('');

    // Popula o formulário quando o usuário (prop) muda
    useEffect(() => {
        if (user) {
            setEmail(user.email || '');
            setRole(user.role || 'user');
            setPlanStatus(user.plan_status || 'free');
            setPageCount(user.page_count || 0);
            setError('');
        }
    }, [user]);

    const handleSubmit = (e) => {
        e.preventDefault();
        setError('');

        const pageCountNum = parseInt(pageCount, 10);
        if (isNaN(pageCountNum) || pageCountNum < 0) {
            setError('Contagem de páginas deve ser um número não-negativo.');
            return;
        }

        const updates = {
            email: email,
            role: role,
            plan_status: planStatus,
            page_count: pageCountNum,
        };

        onConfirm(user.id, updates); // Envia o ID e os dados atualizados
    };

    if (!user) {
        return null; // Não renderiza se não houver usuário
    }

    return (
        <div className="modal-overlay">
            <div className="user-edit-modal">
                <h3>Editar Usuário: {user.email}</h3>
                <form onSubmit={handleSubmit}>
                    <div className="input-group">
                        <label htmlFor="editEmail">E-mail:</label>
                        <input
                            type="email"
                            id="editEmail"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                            disabled={isLoading}
                        />
                    </div>
                    <div className="input-group">
                        <label htmlFor="editRole">Nível (role):</label>
                        <select
                            id="editRole"
                            value={role}
                            onChange={(e) => setRole(e.target.value)}
                            disabled={isLoading}
                        >
                            <option value="user">User</option>
                            <option value="admin">Admin</option>
                        </select>
                    </div>
                    <div className="input-group">
                        <label htmlFor="editPlan">Plano:</label>
                        <select
                            id="editPlan"
                            value={planStatus}
                            onChange={(e) => setPlanStatus(e.target.value)}
                            disabled={isLoading}
                        >
                            <option value="free">Free</option>
                            <option value="past_due">Pagamento Pendente</option>
                            <option value="basic">Básico</option>
                            <option value="standard">Padrão</option>
                            <option value="premium">Premium</option>
                        </select>
                    </div>
                    <div className="input-group">
                        <label htmlFor="editPageCount">Contagem de Páginas:</label>
                        <input
                            type="number"
                            id="editPageCount"
                            value={pageCount}
                            onChange={(e) => setPageCount(e.target.value)}
                            min="0"
                            step="1"
                            required
                            disabled={isLoading}
                        />
                    </div>
                    
                    {error && <p className="modal-error-message">{error}</p>}
                    
                    <div className="modal-actions">
                        <button type="button" onClick={onCancel} disabled={isLoading} className="cancel-button">
                            Cancelar
                        </button>
                        <button type="submit" disabled={isLoading} className="confirm-button">
                            {isLoading ? 'Salvando...' : 'Salvar Alterações'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

export default UserEditModal;
