// /opt/pontua/AutoPonto/poupa-tempo/src/Planos.js
import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { fetchWithAuth } from './apiUtils';
import './Planos.css';

const Planos = ({ onLogout }) => {
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const [infoMessage, setInfoMessage] = useState('');
    const location = useLocation();

    // *** ATENÇÃO: COLOQUE SEUS IDs DE PREÇO (PRICE IDs) DO STRIPE AQUI ***
    // Use os IDs do MODO DE TESTE primeiro.
    const planos = [
        {
            id: 'basic',
            name: 'Básico',
            price: 'R$ 249,90',
            priceDetails: '/ mês',
            pages: '200 páginas',
            extra: 'R$ 1,50',
            stripePriceId: 'price_1SKgd6FKA6J77HjZDbRcv9EC' // <<< SEU ID DE PREÇO BÁSICO FIXO (TESTE)
        },
        {
            id: 'standard',
            name: 'Padrão',
            price: 'R$ 449,90',
            priceDetails: '/ mês',
            pages: '500 páginas',
            extra: 'R$ 1,10',
            stripePriceId: 'price_1SKhg6FKA6J77HjZV3x3YWzI' // <<< SEU ID DE PREÇO PADRÃO FIXO (TESTE)
        },
        {
            id: 'premium',
            name: 'Premium',
            price: 'R$ 999,90',
            priceDetails: '/ mês',
            pages: '1.500 páginas',
            extra: 'R$ 0,75',
            stripePriceId: 'price_1SKhjBFKA6J77HjZkvvuWOB0' // <<< SEU ID DE PREÇO PREMIUM FIXO (TESTE)
        },
    ];

    // Verifica parâmetros da URL ao carregar
    useEffect(() => {
        const params = new URLSearchParams(location.search);
        if (params.get('canceled') === 'true') {
            setInfoMessage('O processo de pagamento foi cancelado. Você pode tentar novamente.');
        }
        if (params.get('status') === 'past_due') {
            setError('Seu último pagamento falhou. Por favor, escolha um plano para atualizar seu método de pagamento e reativar sua conta.');
        }
    }, [location]);


    const handleSelectPlan = async (priceId) => {
        setIsLoading(true);
        setError('');
        setInfoMessage('');
        console.log("Selecionado plano com Price ID:", priceId);

        try {
            const response = await fetchWithAuth('/api/create-checkout-session', {
                method: 'POST',
                body: JSON.stringify({ priceId: priceId }),
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ msg: "Erro desconhecido" }));
                if (response.status !== 401) {
                    setError(errorData.msg || "Falha ao criar sessão de checkout.");
                }
                throw new Error(errorData.msg || `Erro ${response.status}`);
            }

            const session = await response.json();
            if (session.url) {
                window.location.href = session.url; // Redireciona para o Stripe
            } else {
                setError("Não foi possível obter a URL de pagamento.");
            }

        } catch (error) {
            console.error("Erro ao iniciar o checkout:", error);
            if (error.message !== 'Sessão expirada ou inválida.' && error.message !== 'Não autenticado.') {
               setError(`Erro: ${error.message}. Tente novamente.`);
            }
        } finally {
            setIsLoading(false);
        }
    };


    return (
        <div className="planos-page-wrapper">
            <header className="planos-header">
                <h1>Escolha seu Plano</h1>
                <button onClick={onLogout} className="planos-logout-button">
                    Sair
                </button>
            </header>
            <main className="planos-container">
                <p className="planos-subheader">
                    Você precisa de um plano ativo para processar seus arquivos.
                </p>

                {error && <p className="planos-error-message">{error}</p>}
                {infoMessage && <p className="planos-info-message">{infoMessage}</p>}

                <div className="planos-grid">
                    {planos.map(plano => (
                        <div key={plano.id} className="plano-card">
                            <h2 className="plano-card-title">{plano.name}</h2>
                            <div className="plano-card-price">
                                {plano.price}
                                <span className="plano-card-price-details">{plano.priceDetails}</span>
                            </div>
                            <ul className="plano-card-features">
                                <li>{plano.pages} incluídas</li>
                                <li><span className="plano-extra-highlight">{plano.extra}</span> por página extra</li>
                            </ul>
                            <button
                                onClick={() => handleSelectPlan(plano.stripePriceId)}
                                className="plano-select-button"
                                disabled={isLoading}
                            >
                                {isLoading ? 'Aguarde...' : 'Selecionar Plano'}
                            </button>
                        </div>
                    ))}
                </div>
            </main>
        </div>
    );
};

export default Planos;
