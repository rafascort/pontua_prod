// /opt/pontua/AutoPonto/poupa-tempo/src/TermsOfServiceModal.js
import React, { useState, useRef } from 'react';
import './TermsOfServiceModal.css';

const TermsOfServiceModal = ({ show, onClose, onAccept }) => {
    const [isScrolledToBottom, setIsScrolledToBottom] = useState(false);
    const contentRef = useRef(null);

    if (!show) {
        return null;
    }

    const handleScroll = () => {
        if (contentRef.current) {
            const { scrollTop, scrollHeight, clientHeight } = contentRef.current;
            // Verifica se o usuário rolou até o final (com uma tolerância de 5px)
            if (scrollTop + clientHeight >= scrollHeight - 5) {
                setIsScrolledToBottom(true);
            }
        }
    };

    // Se não há onAccept (modo de aceite), considera "rolado" para habilitar o botão de fechar se onAccept não existir
    // Mas no modo de aceite (onAccept existe), isScrolledToBottom deve ser true.
    const canAccept = onAccept ? isScrolledToBottom : true;


    return (
        <div className="terms-modal-overlay">
            <div className="terms-modal">
                <h3>TERMO DE USO E SERVIÇO – SISTEMA PONTO</h3>
                <div className="terms-content" onScroll={handleScroll} ref={contentRef}>
                    {/* Conteúdo extraído do TERMO DE USO E SERVIÇO V3.docx */}
                    <p><strong>Versão 2.0 – Novembro/2025</strong></p>
                    <p>Bem-vindo ao Sistema Ponto, software desenvolvido por SISTEMA PONTO LTDA, pessoa jurídica de direito privado, com sede em Passo Fundo/RS, doravante denominada LICENCIANTE.Ao acessar e utilizar o sistema, o usuário (LICENCIADO) declara ter lido, compreendido e aceitado integralmente os termos abaixo.</p>
                    
                    <h4>1. OBJETO</h4>
                    <p>O Sistema Ponto é uma ferramenta de automação que realiza a leitura e interpretação de cartões ponto, gerando planilhas para uso em perícias contábeis e trabalhistas. A licença concedida é não exclusiva, intransferível e limitada ao plano contratado.</p>
                    
                    <h4>2. ORIENTAÇÕES SOBRE O USO DOS MODELOS DE LEITURA DE CARTÕES PONTO</h4>
                    <p>O Sistema Ponto dispõe de dois modelos de inteligência artificial (IA) destinados à leitura dos cartões ponto, sendo de responsabilidade exclusiva do LICENCIADO a escolha adequada do modelo conforme o tipo de arquivo a ser processado:</p>
                    <p>I – “IA Geral (Com Data)”: deve ser utilizada quando o cartão ponto for originado de documento digital nativo (selecionável) e contiver datas no formato dd/mm/aaaa ou dd/mm/aa.</p>
                    <p>II – “IA Geral (Sem Data)”: deve ser utilizada quando o cartão ponto tiver sido digitalizado (imagem escaneada), manuscrito ou não contiver datas no formato mencionado acima.</p>
                    <p>A precisão dos resultados depende diretamente da correta seleção do modelo de IA e da qualidade dos arquivos submetidos. Em se tratando de cartões manuscritos ou com rasuras, a leitura automática poderá apresentar variações equivalentes à interpretação humana, sendo mera estimativa probabilística.</p>
                    <p>A LICENCIANTE não se responsabiliza por inconsistências, imprecisões ou divergências resultantes da utilização inadequada dos modelos de IA, do envio de arquivos ilegíveis, de baixa resolução ou com formatação incompatível.</p>
                    <p>O uso é restrito ao próprio perito ou escritório contratado.</p>

                    <h4>3. PLANOS, PAGAMENTO E RENOVAÇÃO AUTOMÁTICA</h4>
                    <p>O valor, forma e recorrência de pagamento seguem o plano escolhido. As assinaturas são renovadas automaticamente ao final de cada período de faturamento, salvo se o LICENCIADO solicitar o cancelamento antes do próximo ciclo. O cancelamento pode ser solicitado a qualquer momento pelos canais oficiais. O não pagamento por mais de 15 dias poderá suspender o acesso. A LICENCIANTE poderá atualizar a tabela de preços mediante aviso prévio de 15 dias.</p>

                    <h4>4. SEGURANÇA E PROTEÇÃO DE DADOS (LGPD)</h4>
                    <p>O processamento dos arquivos é temporário e criptografado. Nenhum documento é armazenado após o processamento. A LICENCIANTE atua como operadora de dados, e o perito é o controlador, conforme a Lei nº 13.709/2018 (LGPD). Logs técnicos mínimos podem ser mantidos por até 30 dias, apenas para suporte e auditoria. O LICENCIADO tem o direito de solicitar, a qualquer momento, o acesso, correção ou exclusão de seus dados pessoais, em conformidade com a LGPD, mediante envio de solicitação ao canal de contato oficial.</p>

                    <h4>5. RESPONSABILIDADE E ISENÇÃO DE GARANTIAS</h4>
                    <p>O Sistema Ponto é uma ferramenta de apoio técnico, e não substitui a análise do perito. O LICENCIANTE não se responsabiliza por erros de leitura, falhas de conexão, má qualidade dos arquivos ou uso indevido dos resultados. O usuário reconhece que utiliza o serviço por sua conta e risco, estando ciente de que o sistema é disponibilizado 'no estado em que se encontra', sem garantias de disponibilidade contínua ou de resultados livres de erro.</p>
                    
                    <h4>6. SUPORTE E DISPONIBILIDADE</h4>
                    <p>O suporte técnico é oferecido em horário comercial, via e-mail, WhatsApp ou outro canal indicado no site oficial. A LICENCIANTE emprega as melhores práticas de estabilidade, podendo realizar manutenções periódicas sem aviso prévio.</p>
                    
                    <h4>7. CONFIDENCIALIDADE</h4>
                    <p>Todas as informações processadas são tratadas de forma confidencial e restrita à execução do serviço. Não há compartilhamento de dados com terceiros, salvo obrigação legal. O LICENCIADO compromete-se também a manter o sigilo de suas credenciais e dos resultados obtidos no uso do sistema.</p>
                    
                    <h4>8. RESCISÃO</h4>
                    <p>O usuário pode cancelar o serviço a qualquer momento. Não há reembolso de valores já pagos, salvo se o serviço não tiver sido disponibilizado. O contrato poderá ser rescindido por descumprimento das cláusulas ou uso indevido do sistema.</p>
                    
                    <h4>9. ALTERAÇÕES DOS TERMOS E POLÍTICA DE PRIVACIDADE</h4>
                    <p>A LICENCIANTE poderá modificar este Termo e a Política de Privacidade a qualquer momento, publicando a nova versão no site oficial. Alterações significativas serão comunicadas por e-mail ou aviso no sistema. O uso contínuo do serviço após a atualização implica aceitação das novas condições.</p>
                    
                    <h4>10. FORO</h4>
                    <p>Fica eleito o foro da comarca de Passo Fundo/RS para dirimir eventuais conflitos, com renúncia a qualquer outro.</p>
                    <p style={{textAlign: 'center', fontWeight: 'bold', marginTop: '15px'}}>Ao clicar em “Li e Aceito os Termos de Uso”, o usuário declara estar ciente e de acordo com todas as condições acima.</p>
                </div>
                <div className="terms-actions">
                    {/* Só mostra o botão Fechar se a função onClose foi passada E a função onAccept NÃO foi */}
                    {onClose && !onAccept && (
                        <button onClick={onClose} className="terms-button secondary">
                            Fechar
                        </button>
                    )}
                    {/* Só mostra o botão Aceitar se a função onAccept foi passada */}
                    {onAccept && (
                        <button 
                            onClick={onAccept} 
                            className="terms-button primary" 
                            disabled={!canAccept}
                            title={!canAccept ? "Role até o final para aceitar" : ""}
                        >
                            Li e Aceito os Termos de Uso
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};

export default TermsOfServiceModal;
