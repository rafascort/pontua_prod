// /opt/pontua/AutoPonto/poupa-tempo/src/UserProfileModal.js
import React, { useState, useEffect, useCallback } from 'react';
import { fetchWithAuth } from './apiUtils';
import { toast } from 'react-toastify';
import './UserProfileModal.css'; // Criaremos este CSS

// Limites dos planos (precisam corresponder aos seus planos Stripe/backend)
const PLAN_LIMITS = {
    free: 0,
    basic: 200,
    standard: 500,
    premium: 1500,
    // Adicione outros status se houver (ex: past_due pode ter um limite associado?)
    past_due: 0 // Ou o limite do plano anterior? Definir como 0 por segurança.
};

// Nomes amigáveis para os planos
const PLAN_NAMES = {
    free: 'Gratuito',
    basic: 'Básico',
    standard: 'Padrão',
    premium: 'Premium',
    past_due: 'Pagamento Pendente',
    inactive: 'Inativo'
    // Adicione outros se necessário
};

const UserProfileModal = ({ show, onClose }) => {
    const [userData, setUserData] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');

    const fetchUserData = useCallback(async () => {
        setIsLoading(true);
        setError('');
        try {
            const response = await fetchWithAuth('/api/user/me');
            if (!response.ok) {
                 const errorData = await response.json().catch(() => ({ msg: 'Erro ao buscar dados do perfil.' }));
                 if (response.status !== 401) { // 401 é tratado globalmente
                    throw new Error(errorData.msg);
                 }
                 return; // Se for 401, handleUnauthorized cuidará
            }
            const data = await response.json();
            setUserData(data);
        } catch (err) {
             if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') {
                setError('Não foi possível carregar os dados do perfil. Tente novamente.');
                toast.error('Erro ao carregar dados do perfil.');
             }
             // Erro de autenticação será tratado pelo apiUtils
        } finally {
            setIsLoading(false);
        }
    }, []); // Não depende de nada externo que mude

    // Busca os dados quando o modal é aberto
    useEffect(() => {
        if (show) {
            fetchUserData();
        } else {
            // Limpa dados quando o modal fecha
            setUserData(null);
            setError('');
        }
    }, [show, fetchUserData]);

    // Calcula páginas extras
    const calculateUsage = () => {
        if (!userData || !userData.plan_status) {
            return { includedPages: 0, extraPages: 0, planName: 'N/A' };
        }
        const planKey = userData.plan_status.toLowerCase();
        const limit = PLAN_LIMITS[planKey] ?? 0; // Pega limite ou 0 se não encontrar
        const used = userData.page_count || 0;
        const includedPages = Math.min(used, limit);
        const extraPages = Math.max(0, used - limit);
        const planName = PLAN_NAMES[planKey] ?? userData.plan_status; // Nome amigável ou o status cru

        return { includedPages, extraPages, planName, limit };
    };

    const usage = calculateUsage();

    if (!show) {
        return null;
    }

    return (
        <div className="modal-overlay">
            <div className="user-profile-modal">
                <h3>Perfil e Uso Atual</h3>

                {isLoading && <p className="loading-message">Carregando...</p>}
                {error && <p className="modal-error-message">{error}</p>}

                {userData && !isLoading && !error && (
                    <div className="profile-details">
                        <div className="profile-item">
                            <span className="profile-label">Email:</span>
                            <span className="profile-value">{userData.email}</span>
                        </div>
                        <div className="profile-item">
                            <span className="profile-label">Plano Atual:</span>
                            <span className="profile-value">{usage.planName}</span>
                        </div>
                         <div className="profile-item">
                            <span className="profile-label">Limite Mensal:</span>
                            <span className="profile-value">{usage.limit} páginas</span>
                        </div>
                        <hr className="separator" />
                        <h4>Uso na Mensalidade Atual</h4>
                        <div className="profile-item">
                            <span className="profile-label">Páginas Processadas:</span>
                            <span className="profile-value">{userData.page_count ?? 0}</span>
                        </div>
                        <div className="profile-item">
                            <span className="profile-label">Páginas Extras Utilizadas:</span>
                            <span className="profile-value">{usage.extraPages}</span>
                        </div>
                        {/* <div className="profile-item">
                            <span className="profile-label">Próximo Fechamento:</span>
                            <span className="profile-value">--/--/---- (A implementar)</span>
                        </div> */}
                    </div>
                )}

                <div className="modal-actions">
                    <button onClick={onClose} className="close-button">
                        Fechar
                    </button>
                </div>
            </div>
        </div>
    );
};

export default UserProfileModal;
