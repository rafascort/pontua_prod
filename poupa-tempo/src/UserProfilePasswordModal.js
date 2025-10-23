// /opt/pontua/AutoPonto/poupa-tempo/src/UserProfilePasswordModal.js
import React, { useState } from 'react';
import { fetchWithAuth } from './apiUtils'; // Para chamar a API de alteração
import { toast } from 'react-toastify'; // Para notificações
import './UserProfilePasswordModal.css'; // Usaremos um CSS parecido com o outro modal

const UserProfilePasswordModal = ({ show, onClose }) => {
    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');

        if (!currentPassword) {
            setError('Por favor, digite sua senha atual.');
            return;
        }
        if (newPassword.length < 6) {
            setError('A nova senha deve ter pelo menos 6 caracteres.');
            return;
        }
         if (!/\d/.test(newPassword)) {
             setError('A nova senha precisa ter pelo menos 1 número.'); return;
         }
         if (!/[!@#$%^&*(),.?":{}|<>]/.test(newPassword)) {
               setError('A nova senha precisa ter pelo menos 1 caractere especial.'); return;
         }
        if (newPassword !== confirmPassword) {
            setError('As novas senhas não coincidem.');
            return;
        }

        setIsLoading(true);
        try {
            const response = await fetchWithAuth('/api/user/password', { // Chama a API correta
                method: 'PUT',
                body: JSON.stringify({ currentPassword, newPassword }),
            });

            const data = await response.json();

            if (response.ok) {
                toast.success(data.msg || "Senha alterada com sucesso!");
                handleClose(); // Fecha o modal
            } else {
                 // Trata erro 401 (senha atual incorreta) ou outros erros da API
                 setError(data.msg || 'Erro ao alterar a senha.');
            }
        } catch (err) {
             if (err.message !== 'Sessão expirada ou inválida.' && err.message !== 'Não autenticado.') {
                setError('Erro de rede ao tentar alterar a senha.');
             }
             // Erro de autenticação será tratado pelo apiUtils
        } finally {
            setIsLoading(false);
        }
    };

    // Função para fechar e limpar o modal
    const handleClose = () => {
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');
        setError('');
        setIsLoading(false);
        onClose(); // Chama a função passada por props para fechar
    };

    // Não renderiza nada se show for false
    if (!show) {
        return null;
    }

    return (
        <div className="modal-overlay">
            <div className="user-profile-password-modal">
                <h3>Alterar Minha Senha</h3>
                <form onSubmit={handleSubmit}>
                    <div className="input-group">
                        <label htmlFor="currentPassword">Senha Atual:</label>
                        <input
                            type="password"
                            id="currentPassword"
                            value={currentPassword}
                            onChange={(e) => setCurrentPassword(e.target.value)}
                            required
                            disabled={isLoading}
                        />
                    </div>
                    <div className="input-group">
                        <label htmlFor="newPasswordModal">Nova Senha:</label>
                        <input
                            type="password"
                            id="newPasswordModal"
                            value={newPassword}
                            onChange={(e) => setNewPassword(e.target.value)}
                            placeholder="Mín. 6 caracteres, 1 número, 1 especial"
                            required
                            disabled={isLoading}
                        />
                    </div>
                    <div className="input-group">
                        <label htmlFor="confirmPasswordModal">Confirmar Nova Senha:</label>
                        <input
                            type="password"
                            id="confirmPasswordModal"
                            value={confirmPassword}
                            onChange={(e) => setConfirmPassword(e.target.value)}
                            required
                            disabled={isLoading}
                        />
                    </div>

                    {error && <p className="modal-error-message">{error}</p>}

                    <div className="modal-actions">
                        {/* Chama handleClose ao invés de onCancel diretamente */}
                        <button type="button" onClick={handleClose} disabled={isLoading} className="cancel-button">
                            Cancelar
                        </button>
                        <button type="submit" disabled={isLoading} className="confirm-button">
                            {isLoading ? 'Salvando...' : 'Salvar Nova Senha'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

export default UserProfilePasswordModal;
