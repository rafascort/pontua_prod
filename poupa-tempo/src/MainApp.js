// /opt/pontua/AutoPonto/poupa-tempo/src/MainApp.js
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { fetchWithAuth } from './apiUtils';
import ProgressModal from './ProgressModal';
import UserProfilePasswordModal from './UserProfilePasswordModal'; // <-- IMPORTA O MODAL CORRETO
import PeriodConfirmationModal from './PeriodConfirmationModal';
import { ToastContainer, toast } from 'react-toastify';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { 
    faSignOutAlt, faUserShield, faKey, faFilePdf, 
    faUpload, faTrash, faFileInvoice, faSync 
} from '@fortawesome/free-solid-svg-icons';
import './App.css'; // Estilos gerais
import './ProgressModal.css'; // Estilos do modal de progresso
import './PeriodConfirmationModal.css'; // Estilos do modal de período
import './UserProfilePasswordModal.css'; // <-- IMPORTA O NOVO CSS

const API_BASE_URL = '/api';

// --- Modelos Disponíveis (Seu código original) ---
const MODEL_IMAGE_PATHS = {
    '1': process.env.PUBLIC_URL + '/Modelo1.png', // JBS
    '6': process.env.PUBLIC_URL + '/Modelo_IA_Geral.png', // IA Sem Data
    '7': process.env.PUBLIC_URL + '/Modelo_IA_Geral.png', // IA Com Data
};
const modelNames = {
    '1': 'JBS Ponto',
    '6': 'IA Geral (Sem Data)',
    '7': 'IA Geral (Com Data)',
};
// --- Fim Modelos ---


const MainApp = ({ onLogout, isAdmin }) => {
    // --- Estados (Seu código original + novos) ---
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
    const [showPasswordModal, setShowPasswordModal] = useState(false); // <-- Estado para o *novo* modal de senha

    // --- Funções (Seu código original + gerenciamento de assinatura) ---

    useEffect(() => {
        return () => {
            if (progressIntervalRef.current) {
                clearInterval(progressIntervalRef.current);
            }
        };
    }, []);

    const resetExtractorState = () => {
        // ... (seu código original de reset) ...
         setModelType(null);
         setSelectedFile(null);
         setPageRange('');
         setSearchTerm('');
         setIsLoading(false);
         setShowProgressModal(false);
         setShowPeriodModal(false);
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
    };

    const checkProgress = async (taskId, isPeriodExtraction = false) => {
        // ... (seu código original de checkProgress) ...
         try {
             const response = await fetchWithAuth(`${API_BASE_URL}/progress/${taskId}`);
             if (!response.ok) {
                 const errorData = await response.json();
                 throw new Error(errorData.error || 'Erro ao verificar progresso.');
             }
             const data = await response.json();
             setProgressData(data);

             if (data.status === 'completed' || data.status === 'error') {
                 clearInterval(progressIntervalRef.current);
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
    };

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
         // Limpa o input para permitir selecionar o mesmo arquivo novamente
         if (fileInputRef.current) {
             fileInputRef.current.value = null;
         }
    };

    const handleUploadClick = () => {
        fileInputRef.current.click();
    };

    const handleCardClick = (modelId) => {
        setModelType(modelId);
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
            if (!response.ok) { const d = await response.json(); throw new Error(d.error || 'Falha.'); }
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
             if (!response.ok) { const d = await response.json(); throw new Error(d.error || 'Falha.'); }
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
             if (!response.ok) { const d = await response.json(); throw new Error(d.error || 'Falha.'); }
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
            console.error("Erro ao criar sessão do portal:", error);
            toast.error(`Erro ao abrir portal: ${error.message}`);
            setIsManagingSubscription(false);
        }
    };

    const renderHeader = () => (
        <header className="top-bar">
             <button
                className="icon-button"
                onClick={() => { setView('home'); resetExtractorState(); }}
                title="Voltar ao início"
            >
                <span className="material-symbols-outlined">home</span>
            </button>
            <h1 className="title">{view === 'extractor' ? 'Extrator de Ponto' : 'Sistema Ponto'}</h1>
            <div style={{display: 'flex', alignItems: 'center', gap: '10px'}}>
                {!isAdmin && (
                    <button
                        onClick={handleManageSubscription}
                        className="header-button" // Reutiliza estilo se houver
                        disabled={isManagingSubscription}
                        title="Gerenciar sua assinatura e pagamentos"
                    >
                        <FontAwesomeIcon icon={faFileInvoice} /> {isManagingSubscription ? "Aguarde..." : "Assinatura"}
                    </button>
                )}
                {isAdmin && (
                    <button className="icon-button" title="Painel de Administração" onClick={() => (window.location.href = '/admin')}>
                        <span className="material-symbols-outlined">admin_panel_settings</span>
                    </button>
                )}
                <button
                    onClick={() => setShowPasswordModal(true)} // <-- Abre o modal correto
                    className="header-button" // Reutiliza estilo se houver
                    title="Alterar sua senha"
                >
                    <FontAwesomeIcon icon={faKey} /> Alterar Senha
                </button>
                <button onClick={onLogout} className="icon-button" title="Sair">
                    <span className="material-symbols-outlined">logout</span>
                </button>
            </div>
        </header>
    );

    // --- JSX (Seu código original com o modal correto) ---
    return (
        <div className="sistema-ponto-container">
            <ToastContainer position="top-right" autoClose={5000} hideProgressBar={false} />
            {renderHeader()}
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
                                onChange={(e) => setSearchTerm(e.target.value)}
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

            {/* ** USA O NOVO MODAL DE SENHA DO USUÁRIO ** */}
            <UserProfilePasswordModal
                show={showPasswordModal}
                onClose={() => setShowPasswordModal(false)}
            />
        </div>
    );
};

export default MainApp;
