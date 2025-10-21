import React, { useState } from 'react';
import './PasswordResetModal.css'; // Criaremos este CSS a seguir

const PasswordResetModal = ({ userEmail, onConfirm, onCancel, isLoading }) => {
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [error, setError] = useState('');

    const handleSubmit = (e) => {
        e.preventDefault();
        setError(''); // Limpa erro anterior
        if (!newPassword || newPassword.length < 6) {
            setError('A senha deve ter pelo menos 6 caracteres.');
            return;
        }
        if (newPassword !== confirmPassword) {
            setError('As senhas não coincidem.');
            return;
        }
        onConfirm(newPassword); // Envia a nova senha para a função de confirmação
    };

    return (
        <div className="modal-overlay">
            <div className="password-modal">
                <h3>Resetar Senha para {userEmail}</h3>
                <form onSubmit={handleSubmit}>
                    <div className="input-group">
                        <label htmlFor="newPassword">Nova Senha:</label>
                        <input
                            type="password"
                            id="newPassword"
                            value={newPassword}
                            onChange={(e) => setNewPassword(e.target.value)}
                            placeholder="Mínimo 6 caracteres"
                            required
                            disabled={isLoading}
                        />
                    </div>
                    <div className="input-group">
                        <label htmlFor="confirmPassword">Confirmar Nova Senha:</label>
                        <input
                            type="password"
                            id="confirmPassword"
                            value={confirmPassword}
                            onChange={(e) => setConfirmPassword(e.target.value)}
                            placeholder="Repita a nova senha"
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
                            {isLoading ? 'Aguarde...' : 'Confirmar'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};

export default PasswordResetModal;
