// /opt/pontua/AutoPonto/poupa-tempo/src/PaymentSuccess.js
import React, { useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './Planos.css'; // Reutilizar CSS

const PaymentSuccess = () => {
    const navigate = useNavigate();

    // Redireciona para o app principal após 5 segundos
    useEffect(() => {
        const timer = setTimeout(() => {
            navigate('/app', { replace: true });
        }, 5000); 

        return () => clearTimeout(timer);
    }, [navigate]);

    return (
        <div className="planos-page-wrapper">
            <div className="planos-container" style={{ textAlign: 'center', paddingTop: '10vh' }}>
                 <h1 style={{ color: '#28a745', marginBottom: '20px' }}>Pagamento Bem-Sucedido!</h1>
                 <p className="planos-subheader" style={{ fontSize: '1.1rem' }}>
                    Seu plano foi ativado. Você será redirecionado para a aplicação em 5 segundos.
                 </p>
                 <Link to="/app" className="plano-select-button" style={{ marginTop: '30px', textDecoration: 'none' }}>
                     Ir para a Aplicação Agora
                 </Link>
            </div>
        </div>
    );
};

export default PaymentSuccess;
