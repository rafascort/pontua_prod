// /opt/pontua/AutoPonto/poupa-tempo/src/Planos.js
import React from 'react';
// import { fetchWithAuth } from './apiUtils'; // Importe se/quando implementar o checkout
import './Planos.css'; // Importa o CSS dedicado

// Componente Planos
const Planos = ({ onLogout }) => {
    // Definição dos planos (baseado na imagem image_b23598.png)
    const planos = [
        { 
            id: 'basic', 
            name: 'Básico', 
            price: 'R$ 249,90', 
            priceDetails: '/ mês',
            pages: '200 páginas', 
            extra: 'R$ 1,50',
            stripePriceId: 'price_SEU_ID_BASICO_AQUI' // Substitua pelo ID real do Stripe
        },
        { 
            id: 'standard', 
            name: 'Padrão', 
            price: 'R$ 449,90', 
            priceDetails: '/ mês',
            pages: '500 páginas', 
            extra: 'R$ 1,10',
            stripePriceId: 'price_SEU_ID_PADRAO_AQUI' // Substitua pelo ID real do Stripe
        },
        { 
            id: 'premium', 
            name: 'Premium', 
            price: 'R$ 999,90', 
            priceDetails: '/ mês',
            pages: '1.500 páginas', 
            extra: 'R$ 0,75',
            stripePriceId: 'price_SEU_ID_PREMIUM_AQUI' // Substitua pelo ID real do Stripe
        },
    ];

    const handleSelectPlan = async (priceId) => {
        // *** AQUI ENTRARÁ A LÓGICA DO STRIPE CHECKOUT ***
        console.log("Selecionado plano com Price ID:", priceId);
        alert("Integração com Stripe Checkout ainda não implementada. Substitua os 'priceId' no código e implemente a chamada de backend.");
        
        // Exemplo da lógica de chamada ao backend (descomente quando a API estiver pronta)
        /*
        try {
            // 1. Chamar seu backend para criar a sessão
            const response = await fetchWithAuth('/api/create-checkout-session', {
                method: 'POST',
                body: JSON.stringify({ priceId: priceId }), // Envia o ID do preço do Stripe
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.msg || "Falha ao criar sessão de checkout.");
            }

            const session = await response.json();
            
            // 2. Redirecionar o usuário para a URL do Stripe
            window.location.href = session.url; 

        } catch (error) {
            console.error("Erro ao criar sessão de checkout:", error);
            alert(`Erro ao iniciar o pagamento: ${error.message}`);
        }
        */
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
                                {/* Adicione mais features aqui se necessário */}
                            </ul>
                            <button 
                                onClick={() => handleSelectPlan(plano.stripePriceId)} 
                                className="plano-select-button"
                            >
                                Selecionar Plano
                            </button>
                        </div>
                    ))}
                </div>
            </main>
        </div>
    );
};

export default Planos;
