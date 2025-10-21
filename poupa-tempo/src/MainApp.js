// /opt/pontua/AutoPonto/poupa-tempo/src/MainApp.js
import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import ProgressModal from './ProgressModal';
import PeriodConfirmationModal from './PeriodConfirmationModal';
import './App.css';
import './ProgressModal.css';
import './PeriodConfirmationModal.css';
import { fetchWithAuth } from './apiUtils'; // Importa o fetch interceptor
import { isTokenValid } from './authUtils'; // Importa a função de verificação

const API_BASE_URL = '/api'; // Define a base da URL da API

// --- ALTERAÇÃO AQUI: Manter apenas modelos 1, 6, 7 ---
const MODEL_IMAGE_PATHS = {
    '1': process.env.PUBLIC_URL + '/Modelo1.png', // JBS
    // '2': process.env.PUBLIC_URL + '/Modelo2.png', // Removido
    // '3': process.env.PUBLIC_URL + '/Modelo3.png', // Removido
    // '4': process.env.PUBLIC_URL + '/Modelo4.png', // Removido
    // '5': process.env.PUBLIC_URL + '/Modelo5.png', // Removido
    '6': process.env.PUBLIC_URL + '/Modelo_IA_Geral.png', // IA Sem Data
    '7': process.env.PUBLIC_URL + '/Modelo_IA_Geral.png', // IA Com Data
};

// --- ALTERAÇÃO AQUI: Manter apenas nomes dos modelos 1, 6, 7 ---
const modelNames = {
    '1': 'JBS Ponto',
    // '2': 'BRF Ponto', // Removido
    // '3': 'PontoMais Web', // Removido
    // '4': 'Minuano Web', // Removido
    // '5': 'Rudder / Planalto', // Removido
    '6': 'IA Geral (Sem Data)', // Modelo sem DD/MM/AAAA
    '7': 'IA Geral (Com Data)', // Modelo com DD/MM/AAAA
};
// --- FIM DAS ALTERAÇÕES ---

function MainApp({ onLogout, isAdmin }) {
    const navigate = useNavigate();
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

    // Pré-carrega as imagens dos modelos
    useEffect(() => {
        Object.values(MODEL_IMAGE_PATHS).forEach(path => {
            if (path) new Image().src = path;
        });
    }, []);

    // Limpa o intervalo de progresso ao desmontar
    useEffect(() => {
        return () => {
            if (progressIntervalRef.current) {
                clearInterval(progressIntervalRef.current);
            }
        };
    }, []);

    // Reseta o estado do extrator
    const resetExtractorState = () => {
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

    // --- ALTERAÇÃO AQUI: Função de verificação de token ---
    const ensureAuthenticated = () => {
        if (!isTokenValid()) {
            console.warn("Ação interrompida: Token inválido ou expirado.");
            alert('A sua sessão expirou ou é inválida. Por favor, faça login novamente.');
            onLogout(); // Chama a função de logout do App.js
            return false;
        }
        return true;
    };
    // --- FIM DA ALTERAÇÃO ---

    const handleFileSelect = (event) => {
        const file = event.target.files[0];
        if (file && file.type === 'application/pdf') {
            setSelectedFile(file);
        } else {
            setSelectedFile(null);
            if (file) {
                alert('Por favor, selecione um ficheiro PDF.');
            }
        }
    };

    const handleUploadClick = () => {
        fileInputRef.current.click();
    };

    const handleCardClick = (modelId) => {
        setModelType(modelId);
    };

    // Função unificada para verificar progresso
    const checkProgress = async (taskId, isPeriodExtraction = false) => {
        try {
            // --- ALTERAÇÃO AQUI: Usa fetchWithAuth ---
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
                                // --- ALTERAÇÃO AQUI: Usa fetchWithAuth ---
                                const downloadResponse = await fetchWithAuth(`${API_BASE_URL}/download/${taskId}`);
                                if (downloadResponse.ok) {
                                    const blob = await downloadResponse.blob();
                                    const url = window.URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    a.href = url;
                                    a.download = data.filename || 'resultado.csv';
                                    document.body.appendChild(a);
                                    a.click(); a.remove(); window.URL.revokeObjectURL(url);
                                    setTimeout(() => { setShowProgressModal(false); resetExtractorState(); }, 3000);
                                } else { throw new Error('Falha ao iniciar o download.'); }
                            } catch (downloadError){
                                setProgressData(prev => ({ ...prev, message: `Erro no download: ${downloadError.message}`, status: 'error' }));
                                setTimeout(() => { setShowProgressModal(false); resetExtractorState(); }, 5000);
                            }
                        } else {
                             console.warn("Processamento concluído sem ficheiro.");
                             setTimeout(() => { setShowProgressModal(false); resetExtractorState(); }, 5000);
                        }
                    }
                } else { // Status === 'error'
                    console.error("Erro na tarefa:", data.error);
                    setTimeout(() => { setShowProgressModal(false); resetExtractorState(); }, 5000);
                }
            }
        } catch (error) {
            // --- ALTERAÇÃO AQUI: Não trata erro de sessão (apiUtils.js já tratou) ---
            if (error.message !== 'Sessão expirada ou inválida.' && error.message !== 'Não autenticado.') {
                console.error("Erro ao verificar progresso:", error);
                setProgressData(prev => ({ ...prev, message: `Erro: ${error.message}`, status: 'error' }));
                setIsLoading(false);
                if (progressIntervalRef.current) { clearInterval(progressIntervalRef.current); progressIntervalRef.current = null; }
                setTimeout(() => { setShowProgressModal(false); resetExtractorState(); }, 5000);
            }
            // --- FIM DA ALTERAÇÃO ---
        }
    };

    // Função chamada ao clicar em "Iniciar"
    const handleStartProcess = () => {
        // --- ALTERAÇÃO AQUI: Verificação de token antes da ação ---
        if (!ensureAuthenticated()) return;
        // --- FIM DA ALTERAÇÃO ---

        if (!modelType) { alert('Por favor, selecione um modelo.'); return; }
        if (!selectedFile) { alert('Por favor, importe um ficheiro PDF.'); return; }
        if (!pageRange && modelType !== '7') {
             alert('Por favor, defina as páginas a serem processadas (ex: 1-5, 8).');
             return;
        }

        setIsLoading(true);
        setShowProgressModal(true);

        if (modelType === '7') { // Processamento Direto para IA com Data
            setProgressData({ current_step: 0, total_steps: 1, message: 'Enviando para processamento direto...' });
            handleDirectProcess();
        } else { // Extração de Período para JBS (1) e IA sem Data (6)
            setProgressData({ current_step: 0, total_steps: 1, message: 'Lendo os períodos do PDF...' });
            handleInitialProcess();
        }
    };

    // Função para processamento direto (Modelo 7)
    const handleDirectProcess = async () => {
        // --- ALTERAÇÃO AQUI: Verificação de token (redundante, mas seguro) ---
        if (!ensureAuthenticated()) return;
        // --- FIM DA ALTERAÇÃO ---

        const formData = new FormData();
        formData.append('pdf_file', selectedFile);
        formData.append('pages', pageRange);
        formData.append('model_type', modelType); // Será '7'

        try {
            // --- ALTERAÇÃO AQUI: Usa fetchWithAuth ---
            const response = await fetchWithAuth(`${API_BASE_URL}/process-direct`, { method: 'POST', body: formData });
            if (!response.ok) { const d = await response.json(); throw new Error(d.error || 'Falha.'); }
            const result = await response.json();
            if (result.task_id) {
                 if (progressIntervalRef.current) clearInterval(progressIntervalRef.current);
                 progressIntervalRef.current = setInterval(() => checkProgress(result.task_id, false), 3000);
            } else { throw new Error("API não retornou task_id."); }
        } catch (error) {
             // --- ALTERAÇÃO AQUI: Não trata erro de sessão ---
             if (error.message !== 'Sessão expirada ou inválida.' && error.message !== 'Não autenticado.') {
                setProgressData({ current_step: 1, total_steps: 1, message: `Erro: ${error.message}`, status: 'error' });
                setIsLoading(false);
                setTimeout(() => { setShowProgressModal(false); resetExtractorState(); }, 5000);
            }
            // --- FIM DA ALTERAÇÃO ---
        }
    };

    // Função para iniciar extração de períodos (Modelos 1, 6)
    const handleInitialProcess = async () => {
        // --- ALTERAÇÃO AQUI: Verificação de token (redundante, mas seguro) ---
        if (!ensureAuthenticated()) return;
        // --- FIM DA ALTERAÇÃO ---

        const formData = new FormData();
        formData.append('pdf_file', selectedFile);
        formData.append('pages', pageRange);

        try {
            // --- ALTERAÇÃO AQUI: Usa fetchWithAuth ---
            const response = await fetchWithAuth(`${API_BASE_URL}/extract-periods`, { method: 'POST', body: formData });
             if (!response.ok) { const d = await response.json(); throw new Error(d.error || 'Falha.'); }
            const result = await response.json();
             if (result.task_id) {
                 if (progressIntervalRef.current) clearInterval(progressIntervalRef.current);
                 progressIntervalRef.current = setInterval(() => checkProgress(result.task_id, true), 1500);
             } else { throw new Error("API não retornou task_id."); }
        } catch (error) {
            // --- ALTERAÇÃO AQUI: Não trata erro de sessão ---
            if (error.message !== 'Sessão expirada ou inválida.' && error.message !== 'Não autenticado.') {
                setProgressData({ current_step: 1, total_steps: 1, message: `Erro: ${error.message}`, status: 'error' });
                setIsLoading(false);
                 setTimeout(() => { setShowProgressModal(false); resetExtractorState(); }, 5000);
            }
            // --- FIM DA ALTERAÇÃO ---
        }
    };

    // Função chamada após confirmar os períodos no modal
    const handleConfirmAndProcess = async (confirmedPeriods) => {
        // --- ALTERAÇÃO AQUI: Verificação de token antes da ação ---
        if (!ensureAuthenticated()) { setShowPeriodModal(false); return; }
        // --- FIM DA ALTERAÇÃO ---

        setShowPeriodModal(false);
        setIsLoading(true);
        setShowProgressModal(true);
        setProgressData({ current_step: 0, total_steps: 3, message: 'Enviando para processamento final...' });

        try {
            // --- ALTERAÇÃO AQUI: Usa fetchWithAuth ---
            const response = await fetchWithAuth(`${API_BASE_URL}/process`, {
                method: 'POST',
                body: JSON.stringify({
                    pdf_path: initialPdfPath,
                    pages_with_periods: confirmedPeriods,
                    model_type: modelType, // Envia o tipo de modelo (será 1 ou 6)
                })
            });
            // --- FIM DA ALTERAÇÃO ---

             if (!response.ok) { const d = await response.json(); throw new Error(d.error || 'Falha.'); }
            const result = await response.json();
            if (result.task_id) {
                 if (progressIntervalRef.current) clearInterval(progressIntervalRef.current);
                 progressIntervalRef.current = setInterval(() => checkProgress(result.task_id, false), 3000);
             } else { throw new Error("API não retornou task_id."); }
        } catch (error) {
            // --- ALTERAÇÃO AQUI: Não trata erro de sessão ---
            if (error.message !== 'Sessão expirada ou inválida.' && error.message !== 'Não autenticado.') {
                setProgressData({ current_step: 3, total_steps: 3, message: `Erro: ${error.message}`, status: 'error' });
                setIsLoading(false);
                 setTimeout(() => { setShowProgressModal(false); resetExtractorState(); }, 5000);
            }
            // --- FIM DA ALTERAÇÃO ---
        }
    };

    // Filtra modelos disponíveis (agora só tem 1, 6, 7 em modelNames)
    const availableModels = Object.keys(modelNames).filter(modelId => {
        return modelNames[modelId].toLowerCase().includes(searchTerm.toLowerCase());
    });

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
                {isAdmin && (
                    <button className="icon-button" title="Painel de Administração" onClick={() => navigate('/admin')}>
                        <span className="material-symbols-outlined">admin_panel_settings</span>
                    </button>
                )}
                <button onClick={onLogout} className="icon-button" title="Sair">
                    <span className="material-symbols-outlined">logout</span>
                </button>
            </div>
        </header>
    );

    return (
        <div className="sistema-ponto-container">
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
                                {selectedFile ? `Ficheiro: ${selectedFile.name}` : 'Importar Ficheiro PDF'}
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
                                {isLoading ? 'Processando...' : 'Iniciar'}
                            </button>
                        </div>
                    </div>
                )}
            </main>
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
        </div>
    );
}

export default MainApp;
