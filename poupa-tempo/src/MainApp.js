import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { fetchWithAuth } from './apiUtils';
import ProgressModal from './ProgressModal';
import UserProfilePasswordModal from './UserProfilePasswordModal';
import PeriodConfirmationModal from './PeriodConfirmationModal';
import UserProfileModal from './UserProfileModal';
import TermsOfServiceModal from './TermsOfServiceModal'; // 1. IMPORTAR O MODAL DE TERMOS
import { ToastContainer, toast } from 'react-toastify';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
    faSignOutAlt, faUserShield, faKey, faFilePdf,
    faUpload, faTrash, faFileInvoice, faSync, faUserCircle,
    faLifeRing // <-- 1. ÍCONE DE SUPORTE ADICIONADO
} from '@fortawesome/free-solid-svg-icons';
import './App.css';
import './ProgressModal.css';
import './PeriodConfirmationModal.css';
import './UserProfilePasswordModal.css';
import './UserProfileModal.css';
import './AlertModal.css';
import './TermsOfServiceModal.css'; // 2. IMPORTAR O CSS DO MODAL

const API_BASE_URL = '/api';

// --- Modelos Disponíveis ---
const MODEL_IMAGE_PATHS = {
    '6': process.env.PUBLIC_URL + '/Modelo_IA_Geral.png',
    '7': process.env.PUBLIC_URL + '/Modelo_IA_Geral.png',
};
const modelNames = {
    '6': 'IA Geral (Sem Data)',
    '7': 'IA Geral (Com Data)',
};
// --- Fim Modelos ---

// --- NOVO: Componente do Modal de Alerta (MODIFICADO COM SEU TEXTO) ---
const PdfTypeAlertModal = ({ show, onClose, onConfirm }) => {
    if (!show) return null;

    return (
        <div className="alert-modal-overlay">
            <div className="alert-modal">
                <h3>⚠️ Atenção: Modelo "IA (Com Data)"</h3>
                
                <p style={{fontWeight: 'bold', fontSize: '1.05rem', color: '#333'}}>
                    Este modelo foi selecionado. Use-o SOMENTE nestas condições:
                </p>
                
                <p style={{marginTop: '15px'}}>
                    <strong>1. PDF Selecionável (Nativo Digital):</strong><br/>
                    Você deve conseguir selecionar o texto do PDF com o mouse.
                    (Dica: tente selecionar o texto agora no seu arquivo).
                </p>
                
                <p>
                    <strong>2. Datas no Formato Correto:</strong><br/>
                    As datas devem estar visíveis no formato <strong>dd/mm/aaaa</strong> ou <strong>dd/mm/aa</strong>.
                </p>
                
                <p style={{marginTop: '20px', backgroundColor: '#f4f4f4', padding: '10px 12px', borderRadius: '5px', borderLeft: '4px solid #6c757d', fontSize: '0.9rem', lineHeight: '1.4'}}>
                    Se o seu PDF for uma imagem (escaneado, foto, não selecionável), manuscrito, ou se as datas não seguirem esse formato, clique em <strong>"Voltar"</strong> e escolha o modelo <strong>"IA Geral (Sem Data)"</strong>.
                    <br/><br/>
                    💡 <i>Essa escolha garante a maior precisão na leitura.</i>
                    <br/>
                    ✍ <i>(Obs: Pontos manuscritos são lidos pelo modelo "Sem Data" com precisão similar ao olho humano).</i>
                </p>
                
                <p style={{marginTop: '20px', fontWeight: 'bold', color: '#333', textAlign: 'center'}}>
                    Deseja prosseguir com o modelo "IA (Com Data)"?
                </p>

                <div className="alert-modal-actions">
                    <button onClick={onClose} className="alert-button secondary">Voltar</button>
                    <button onClick={onConfirm} className="alert-button primary">Prosseguir</button>
                </div>
            </div>
        </div>
    );
};
// --- Fim Componente Modal ---

const MainApp = ({ onLogout, isAdmin }) => {
    // --- Estados ---
    const [view, setView] = useState('home');
    const [modelType, setModelType] = useState(null);
    const [selectedFile, setSelectedFile] = useState(null);
    const [pageRange, setPageRange] = useState('');
    const [searchTerm, setSearchTerm] = useState('');
    const [showProgressModal, setShowProgressModal] = useState(false);
    const [progressData, setProgressData] = useState({ current_step: 0, total_steps: 1, message: 'Iniciando...' });
    const [isLoading, setIsLoading] = useState(false);
    const [showPeriodModal, setShowPeriodModal] = useState(false);
    const [pagesInfo, setPagesInfo] = useState([]);
    const [initialPdfPath, setInitialPdfPath] = useState('');
    const fileInputRef = useRef(null);
    const progressIntervalRef = useRef(null);
    const [isManagingSubscription, setIsManagingSubscription] = useState(false);
    const [showPasswordModal, setShowPasswordModal] = useState(false);
    const [showProfileModal, setShowProfileModal] = useState(false);
    
    // ESTADO NOVO PARA O ALERTA
    const [showPdfTypeAlert, setShowPdfTypeAlert] = useState(false);
    
    // 3. ADICIONAR ESTADO PARA O MODAL DE TERMOS
    const [showTermsModalForAcceptance, setShowTermsModalForAcceptance] = useState(false);

    // --- Funções ---

    // 4. ADICIONAR useEffect PARA VERIFICAR OS TERMOS
    useEffect(() => {
        const hasAccepted = localStorage.getItem('hasAcceptedTerms') === 'true';
        
        // Se os termos não foram aceitos E o usuário NÃO é admin, mostre o modal.
        if (!hasAccepted && !isAdmin) {
            setShowTermsModalForAcceptance(true);
        }
    }, [isAdmin]); // Depende de `isAdmin` para garantir que a prop foi recebida


    useEffect(() => {
        return () => {
            if (progressIntervalRef.current) {
                clearInterval(progressIntervalRef.current);
            }
        };
    }, []);

    const resetExtractorState = useCallback(() => {
         setModelType(null);
         setSelectedFile(null);
         setPageRange('');
         setSearchTerm('');
         setIsLoading(false);
         setShowProgressModal(false);
         setShowPeriodModal(false);
         setShowPdfTypeAlert(false); // Resetar alerta
         setPagesInfo([]);
         setInitialPdfPath('');
         setProgressData({ current_step: 0, total_steps: 1, message: 'Iniciando...' });
         if (progressIntervalRef.current) {
             clearInterval(progressIntervalRef.current);
             progressIntervalRef.current = null;
         }
         if (fileInputRef.current) {
             fileInputRef.current.value = '';
         }
    },[]);

    const checkProgress = useCallback(async (taskId, isPeriodExtraction = false) => {
        try {
            const response = await fetchWithAuth(`${API_BASE_URL}/progress/${taskId}`);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: 'Erro ao verificar progresso.'}));
                throw new Error(errorData.error || 'Erro ao verificar progresso.');
            }
            const data = await response.json();
            setProgressData(data);

            if (data.status === 'completed' || data.status === 'error') {
                if (progressIntervalRef.current) clearInterval(progressIntervalRef.current);
                progressIntervalRef.current = null;
                setIsLoading(false);

                if (data.status === 'completed') {
                    if (isPeriodExtraction) {
                        setShowProgressModal(false);
                        setPagesInfo(data.result || []);
                        setInitialPdfPath(data.pdf_path || '');
                        setShowPeriodModal(true);
                    } else {
                        if (data.file_path) {
                            try {
                                const downloadResponse = await fetchWithAuth(`${API_BASE_URL}/download/${taskId}`);
                                if (downloadResponse.ok) {
                                    const blob = await downloadResponse.blob();
                                    const url = window.URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    a.href = url;
                                    a.download = data.filename || 'resultado.csv';
                                    document.body.appendChild(a);
                                    a.click(); a.remove(); window.URL.revokeObjectURL(url);
                                    setProgressData(prev => ({ ...prev, message: 'Download concluído!', status: 'completed' }));
                                    toast.success("Processamento e download concluídos!");
                                    setTimeout(() => { setShowProgressModal(false); resetExtractorState(); }, 3000);
                                } else { throw new Error('Falha ao iniciar o download.'); }
                            } catch (downloadError){
                                setProgressData(prev => ({ ...prev, message: `Erro no download: ${downloadError.message}`, status: 'error' }));
                                toast.error(`Erro no download: ${downloadError.message}`);
                                setTimeout(() => { setShowProgressModal(false); resetExtractorState(); }, 5000);
                            }
                        } else {
                             console.warn("Processamento concluído sem ficheiro.");
                             setTimeout(() => { setShowProgressModal(false); resetExtractorState(); }, 5000);
                        }
                    }
                } else { // Status === 'error'
                    console.error("Erro na tarefa:", data.error);
                    setProgressData(prev => ({ ...prev, message: `Erro: ${data.error}`, status: 'error' }));
                    toast.error(`Erro no processamento: ${data.error}`);
                    setTimeout(() => { setShowProgressModal(false); resetExtractorState(); }, 5000);
                }
            }
        } catch (error) {
             if (error.message !== 'Sessão expirada ou inválida.' && error.message !== 'Não autenticado.') {
                console.error("Erro ao verificar progresso:", error);
                setProgressData(prev => ({ ...prev, message: `Erro: ${error.message}`, status: 'error' }));
                setIsLoading(false);
                if (progressIntervalRef.current) { clearInterval(progressIntervalRef.current); progressIntervalRef.current = null; }
                setTimeout(() => { setShowProgressModal(false); resetExtractorState(); }, 5000);
             }
        }
    }, [resetExtractorState]); 

    const handleFileSelect = (event) => {
        const file = event.target.files[0];
        if (file && file.type === 'application/pdf') {
            setSelectedFile(file);
        } else {
            setSelectedFile(null);
            if (file) {
                toast.warn('Por favor, selecione um ficheiro PDF.');
            }
        }
         if (fileInputRef.current) {
             fileInputRef.current.value = null;
         }
    };

    const handleUploadClick = () => {
        fileInputRef.current.click();
    };

    // --- LÓGICA DO CLIQUE (ALTERADA) ---
    const handleCardClick = (modelId) => {
        if (modelId === '7') {
            setShowPdfTypeAlert(true); // Mostra o alerta para o modelo 7
        } else {
            setModelType(modelId);
            setShowPdfTypeAlert(false);
        }
    };

    // --- CONFIRMAÇÃO DO MODAL ---
    const handleConfirmPdfType = () => {
        setModelType('7'); // Seleciona o modelo
        setShowPdfTypeAlert(false); // Fecha o modal
    };

    const handleStartProcess = () => {
        if (!modelType) { toast.warn('Por favor, selecione um modelo.'); return; }
        if (!selectedFile) { toast.warn('Por favor, importe um ficheiro PDF.'); return; }
        if (!pageRange && modelType !== '7') {
             toast.warn('Por favor, defina as páginas a serem processadas (ex: 1-5, 8).');
             return;
        }

        setIsLoading(true);
        setShowProgressModal(true);

        if (modelType === '7') {
            setProgressData({ current_step: 0, total_steps: 1, message: 'Enviando para processamento direto...' });
            handleDirectProcess();
        } else {
            setProgressData({ current_step: 0, total_steps: 1, message: 'Lendo os períodos do PDF...' });
            handleInitialProcess();
        }
    };

    const handleDirectProcess = async () => {
        const formData = new FormData();
        formData.append('pdf_file', selectedFile);
        formData.append('pages', pageRange);
        formData.append('model_type', modelType);

        try {
            const response = await fetchWithAuth(`${API_BASE_URL}/process-direct`, { method: 'POST', body: formData });
            if (!response.ok) { const d = await response.json().catch(() => ({error:'Falha'})); throw new Error(d.error || 'Falha.'); }
            const result = await response.json();
            if (result.task_id) {
                 if (progressIntervalRef.current) clearInterval(progressIntervalRef.current);
                 progressIntervalRef.current = setInterval(() => checkProgress(result.task_id, false), 3000);
            } else { throw new Error("API não retornou task_id."); }
        } catch (error) {
             if (error.message !== 'Sessão expirada ou inválida.' && error.message !== 'Não autenticado.') {
                setProgressData({ current_step: 1, total_steps: 1, message: `Erro: ${error.message}`, status: 'error' });
                setIsLoading(false);
                setTimeout(() => { setShowProgressModal(false); resetExtractorState(); }, 5000);
            }
        }
    };

    const handleInitialProcess = async () => {
        const formData = new FormData();
        formData.append('pdf_file', selectedFile);
        formData.append('pages', pageRange);

        try {
            const response = await fetchWithAuth(`${API_BASE_URL}/extract-periods`, { method: 'POST', body: formData });
             if (!response.ok) { const d = await response.json().catch(() => ({error:'Falha'})); throw new Error(d.error || 'Falha.'); }
            const result = await response.json();
             if (result.task_id) {
                 if (progressIntervalRef.current) clearInterval(progressIntervalRef.current);
                 progressIntervalRef.current = setInterval(() => checkProgress(result.task_id, true), 1500);
             } else { throw new Error("API não retornou task_id."); }
        } catch (error) {
            if (error.message !== 'Sessão expirada ou inválida.' && error.message !== 'Não autenticado.') {
                setProgressData({ current_step: 1, total_steps: 1, message: `Erro: ${error.message}`, status: 'error' });
                setIsLoading(false);
                 setTimeout(() => { setShowProgressModal(false); resetExtractorState(); }, 5000);
            }
        }
    };

    const handleConfirmAndProcess = async (confirmedPeriods) => {
        setShowPeriodModal(false);
        setIsLoading(true);
        setShowProgressModal(true);
        setProgressData({ current_step: 0, total_steps: 3, message: 'Enviando para processamento final...' });

        try {
            const response = await fetchWithAuth(`${API_BASE_URL}/process`, {
                method: 'POST',
                body: JSON.stringify({
                    pdf_path: initialPdfPath,
                    pages_with_periods: confirmedPeriods,
                    model_type: modelType,
                })
            });
             if (!response.ok) { const d = await response.json().catch(() => ({error:'Falha'})); throw new Error(d.error || 'Falha.'); }
            const result = await response.json();
            if (result.task_id) {
                 if (progressIntervalRef.current) clearInterval(progressIntervalRef.current);
                 progressIntervalRef.current = setInterval(() => checkProgress(result.task_id, false), 3000);
             } else { throw new Error("API não retornou task_id."); }
        } catch (error) {
            if (error.message !== 'Sessão expirada ou inválida.' && error.message !== 'Não autenticado.') {
                setProgressData({ current_step: 3, total_steps: 3, message: `Erro: ${error.message}`, status: 'error' });
                setIsLoading(false);
                 setTimeout(() => { setShowProgressModal(false); resetExtractorState(); }, 5000);
            }
        }
    };

    const availableModels = Object.keys(modelNames).filter(modelId => {
        return modelNames[modelId].toLowerCase().includes(searchTerm.toLowerCase());
    });

    const handleManageSubscription = async () => {
        setIsManagingSubscription(true);
        try {
            const response = await fetchWithAuth('/api/create-portal-session', {
                method: 'POST',
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ msg: "Erro desconhecido" }));
                throw new Error(errorData.msg || "Erro ao abrir portal de gerenciamento.");
            }

            const data = await response.json();
            if (data.url) {
                window.location.href = data.url;
            }
        } catch (error) {
             if (error.message !== 'Sessão expirada ou inválida.' && error.message !== 'Não autenticado.') {
                console.error("Erro ao criar sessão do portal:", error);
                toast.error(`Erro ao abrir portal: ${error.message}`);
             }
            setIsManagingSubscription(false);
        }
    };

    // 5. ADICIONAR FUNÇÃO PARA LIDAR COM O ACEITE
    const handleAcceptTerms = () => {
        localStorage.setItem('hasAcceptedTerms', 'true');
        setShowTermsModalForAcceptance(false);
    };

    const renderHeader = () => (
        <header className="top-bar">
             {/* 2. Agrupar botões da esquerda */}
             <div style={{display: 'flex', alignItems: 'center', gap: '10px'}}>
                <button
                    className="icon-button"
                    onClick={() => { setView('home'); resetExtractorState(); }}
                    title="Voltar ao início"
                >
                    <span className="material-symbols-outlined">home</span>
                </button>

                {/* 3. ADICIONAR BOTÃO DE SUPORTE AQUI */}
                <a
                    href="https://wa.link/iuffl7"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="header-button" // Reutiliza o estilo dos botões de usuário
                    title="Suporte via WhatsApp"
                >
                    <FontAwesomeIcon icon={faLifeRing} /> Suporte
                </a>
             </div>
            
            <h1 className="title">{view === 'extractor' ? 'Extrator de Ponto' : 'Sistema Ponto'}</h1>
            
            <div className="user-menu" style={{display: 'flex', alignItems: 'center', gap: '10px'}}>
                <button
                    onClick={() => setShowProfileModal(true)}
                    className="header-button"
                    title="Ver Perfil e Uso"
                >
                    <FontAwesomeIcon icon={faUserCircle} /> Perfil
                </button>
                {!isAdmin && (
                    <button
                        onClick={handleManageSubscription}
                        className="header-button"
                        disabled={isManagingSubscription}
                        title="Gerenciar sua assinatura e pagamentos"
                    >
                        <FontAwesomeIcon icon={faFileInvoice} /> {isManagingSubscription ? "Aguarde..." : "Assinatura"}
                    </button>
                )}
                {isAdmin && (
                    <Link to="/admin" className="header-button" title="Painel de Administração">
                        <FontAwesomeIcon icon={faUserShield} /> Admin
                    </Link>
                )}
                <button
                    onClick={() => setShowPasswordModal(true)}
                    className="header-button"
                    title="Alterar sua senha"
                >
                    <FontAwesomeIcon icon={faKey} /> Alterar Senha
                </button>
                <button onClick={onLogout} className="header-button logout-button" title="Sair">
                    <FontAwesomeIcon icon={faSignOutAlt} /> Sair
                </button>
            </div>
        </header>
    );

    return (
        <div className="sistema-ponto-container">
            <ToastContainer position="top-right" autoClose={5000} hideProgressBar={false} />
            {renderHeader()}

            {/* 6. ADICIONAR O MODAL DE TERMOS PARA ACEITAÇÃO */}
            {/* Ele ficará sobre toda a aplicação se showTermsModalForAcceptance for true */}
            <TermsOfServiceModal
                show={showTermsModalForAcceptance}
                onAccept={handleAcceptTerms}
                // Não passamos onClose, forçando o usuário a aceitar
            />

            <main className="main-content">
                {view === 'home' && (
                    <div className="button-container">
                        <button className="action-button" onClick={() => setView('extractor')}>Extrator de ponto</button>
                        <button className="action-button" disabled>Em breve...</button>
                    </div>
                )}
                {view === 'extractor' && (
                     <div className="extractor-container">
                          <div className="extractor-header">
                            <h2>Selecione o modelo, o ficheiro e as páginas</h2>
                            <input
                                type="text"
                                className="search-bar"
                                placeholder="Pesquisar modelo..."
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.g.value)}
                            />
                        </div>
                        <div className="model-carousel-container">
                            <div className="model-carousel">
                                {availableModels.map(modelId => (
                                    <div
                                        key={modelId}
                                        className={`model-card ${modelType === modelId ? 'selected' : ''}`}
                                        onClick={() => handleCardClick(modelId)}
                                    >
                                        {MODEL_IMAGE_PATHS[modelId] ? (
                                            <img src={MODEL_IMAGE_PATHS[modelId]} alt={`Modelo ${modelNames[modelId]}`} />
                                        ) : (
                                            <div style={{ height: '160px', background: '#2c3e50', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                                <span className="material-symbols-outlined" style={{ fontSize: '60px', color: '#ecf0f1' }}>description</span>
                                            </div>
                                        )}
                                        <p>{modelNames[modelId]}</p>
                                    </div>
                                ))}
                                {availableModels.length === 0 && (
                                    <p style={{ color: '#a8b3c7', textAlign: 'center', gridColumn: '1 / -1' }}>
                                        Nenhum modelo encontrado para "{searchTerm}".
                                    </p>
                                )}
                            </div>
                        </div>
                        <div className="extractor-actions">
                            <input
                                type="file"
                                accept=".pdf"
                                ref={fileInputRef}
                                onChange={handleFileSelect}
                                style={{ display: 'none' }}
                            />
                            <button className="extractor-button" onClick={handleUploadClick} disabled={isLoading}>
                                <FontAwesomeIcon icon={faUpload} /> {selectedFile ? `Ficheiro: ${selectedFile.name.substring(0, 20)}...` : 'Importar Ficheiro PDF'}
                            </button>
                            <input
                                type="text"
                                className="page-input"
                                placeholder={modelType === '7' ? "Páginas (Opcional, ex: 1-5, 8)" : "Páginas (Obrigatório, ex: 1-5, 8)"}
                                value={pageRange}
                                onChange={(e) => setPageRange(e.target.value)}
                                disabled={isLoading || !selectedFile}
                            />
                            <button
                                className="start-button"
                                onClick={handleStartProcess}
                                disabled={isLoading || !modelType || !selectedFile || (!pageRange && modelType !== '7')}
                            >
                                <FontAwesomeIcon icon={faSync} /> {isLoading ? 'Processando...' : 'Iniciar'}
                            </button>
                        </div>
                    </div>
                )}
            </main>

            {/* Modais */}
            
            {/* MODAL DE ALERTA AQUI */}
            <PdfTypeAlertModal 
                show={showPdfTypeAlert}
                onClose={() => setShowPdfTypeAlert(false)}
                onConfirm={handleConfirmPdfType}
            />

            {showProgressModal &&
                <ProgressModal
                    {...progressData}
                    onClose={() => {
                         if (!isLoading && (progressData.status === 'completed' || progressData.status === 'error')) {
                            setShowProgressModal(false);
                            resetExtractorState();
                         } else if (!isLoading) {
                              setShowProgressModal(false);
                         }
                    }}
                />
            }
            {showPeriodModal &&
                <PeriodConfirmationModal
                    pagesInfo={pagesInfo}
                    onConfirm={handleConfirmAndProcess}
                    onCancel={() => { setShowPeriodModal(false); resetExtractorState(); }}
                    isLoading={isLoading}
                />
            }
            <UserProfilePasswordModal
                show={showPasswordModal}
                onClose={() => setShowPasswordModal(false)}
            />
            <UserProfileModal
                show={showProfileModal}
                onClose={() => setShowProfileModal(false)}
            />
        </div>
    );
};

export default MainApp;
