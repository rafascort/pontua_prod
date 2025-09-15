import React, { useState, useRef, useEffect } from 'react';
import ProgressModal from './ProgressModal';
import './App.css'; 

const API_BASE_URL = '/api';

// Mapeamento de caminhos das imagens dos modelos
const MODEL_IMAGE_PATHS = {
    '1': process.env.PUBLIC_URL + '/Modelo1.png',
    '2': process.env.PUBLIC_URL + '/Modelo2.png',
    '3': process.env.PUBLIC_URL + '/Modelo3.png',
    '4': process.env.PUBLIC_URL + '/Modelo4.png',
    '5': process.env.PUBLIC_URL + '/Modelo5.png', // CORRIGIDO: Este é o novo modelo
};

function MainApp({ onLogout }) {
    // --- STATE MANAGEMENT ---
    const [view, setView] = useState('home');
    const [extractorStep, setExtractorStep] = useState(1);
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedFile, setSelectedFile] = useState(null);
    const [pageRange, setPageRange] = useState('');
    const [modelType, setModelType] = useState(null);
    const [zoomedModel, setZoomedModel] = useState(null);
    const [settings, setSettings] = useState({});
    const [statusMessage, setStatusMessage] = useState('Aguardando arquivo...');
    const [isProcessing, setIsProcessing] = useState(false);
    const [showProgressModal, setShowProgressModal] = useState(false);
    const [currentTaskId, setCurrentTaskId] = useState(null);
    const [progressData, setProgressData] = useState({
        current_step: 0,
        total_steps: 1,
        progress: 0,
        message: 'Iniciando...'
    });
    const fileInputRef = useRef(null);
    const progressIntervalRef = useRef(null);

    // --- EFEITOS ---
    useEffect(() => {
        Object.values(MODEL_IMAGE_PATHS).forEach(path => {
            if (path) { new Image().src = path; }
        });
    }, []);

    useEffect(() => {
        return () => {
            if (progressIntervalRef.current) {
                clearInterval(progressIntervalRef.current);
            }
        };
    }, []);

    // --- FUNÇÕES DE MANIPULAÇÃO (Handlers) ---
    const resetExtractorState = () => {
        setView('home');
        setExtractorStep(1);
        setSearchTerm('');
        setSelectedFile(null);
        setPageRange('');
        setModelType(null);
        setStatusMessage('Aguardando arquivo...');
    };

    const handleFileSelect = (event) => {
        const file = event.target.files[0];
        if (file && file.type === 'application/pdf') { setSelectedFile(file); } 
        else { setSelectedFile(null); }
    };
    const handleUploadClick = () => { fileInputRef.current.click(); };

    const handleCardClick = (modelId) => {
        setModelType(modelId);
        setZoomedModel(modelId);
    };
    
    const checkProgress = async (taskId) => {
        const token = localStorage.getItem('jwt_token');
        if (!token) { onLogout(); return; }
        try {
            const response = await fetch(`${API_BASE_URL}/progress/${taskId}`, { headers: { 'Authorization': `Bearer ${token}` } });
            if (response.status === 401 || response.status === 403) { alert('A sua sessão expirou.'); onLogout(); return; }
            if (!response.ok) { throw new Error('Erro ao verificar progresso.'); }
            const data = await response.json();
            setProgressData({ current_step: data.current_step || 0, total_steps: data.total_steps || 1, progress: data.progress || 0, message: data.message || 'A processar...' });
            setStatusMessage(data.message || 'A processar...');
            if (data.status === 'completed' || data.status === 'error') {
                if (progressIntervalRef.current) { clearInterval(progressIntervalRef.current); progressIntervalRef.current = null; }
                setIsProcessing(false); setShowProgressModal(false); setCurrentTaskId(null);
                if (data.status === 'completed') {
                    const downloadResponse = await fetch(`${API_BASE_URL}/download/${taskId}`, { headers: { 'Authorization': `Bearer ${token}` } });
                    if (downloadResponse.ok) {
                        const blob = await downloadResponse.blob();
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a'); a.href = url; a.download = data.filename || 'resultado.csv'; document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url);
                        setStatusMessage(`Processo finalizado! Download iniciado.`);
                        
                        setTimeout(() => {
                            resetExtractorState();
                        }, 3000); 

                    } else { setStatusMessage(`Erro ao descarregar o ficheiro.`); }
                } else { setStatusMessage(`Erro: ${data.error || data.message}`); }
            }
        } catch (error) {
            console.error('Erro de rede:', error); setStatusMessage(`Erro de rede: ${error.message}`); setIsProcessing(false); setShowProgressModal(false); if (progressIntervalRef.current) clearInterval(progressIntervalRef.current);
        }
    };
    const handleProcess = async () => {
        if (!selectedFile || !pageRange || !modelType) { alert('Complete todos os passos.'); return; }
        setIsProcessing(true); setShowProgressModal(true); setProgressData({ current_step: 0, total_steps: 1, progress: 0, message: 'A iniciar...' }); setStatusMessage('A iniciar...');
        const formData = new FormData();
        formData.append('pdf_file', selectedFile); formData.append('pages', pageRange); formData.append('model_type', modelType);
        const token = localStorage.getItem('jwt_token'); if (!token) { onLogout(); return; }
        try {
            const response = await fetch(`${API_BASE_URL}/process`, { method: 'POST', headers: { 'Authorization': `Bearer ${token}` }, body: formData });
            if (!response.ok) { const errorResult = await response.json(); if (response.status === 401 || response.status === 403) { onLogout(); } throw new Error(errorResult.error || errorResult.msg || 'Erro no servidor.'); }
            const result = await response.json();
            setCurrentTaskId(result.task_id);
            progressIntervalRef.current = setInterval(() => checkProgress(result.task_id), 1000);
        } catch (error) {
            console.error('Ocorreu um erro:', error); setStatusMessage(`Erro: ${error.message}`); setIsProcessing(false); setShowProgressModal(false);
        }
    };
    const handleCloseModal = () => { setShowProgressModal(false); };

    const modelNames = { 
        '1': 'JBS Ponto', 
        '2': 'BRF Ponto', 
        '3': 'Ponto Mais', 
        '4': 'Minuano',
        '5': 'Rudder Digital' // CORRIGIDO: Nome do novo modelo
    };

    // --- LÓGICA DE RENDERIZAÇÃO ---
    const renderHeader = () => (
        <header className="top-bar">
            <button className="icon-button" aria-label="Voltar ou Menu" onClick={() => {
                if (view === 'extractor') {
                    if (extractorStep > 1) { setExtractorStep(extractorStep - 1); } 
                    else { setView('home'); }
                }
            }}>
                <span className="material-symbols-outlined">{view === 'extractor' ? 'arrow_back' : 'menu'}</span>
            </button>
            <h1 className="title">{view === 'extractor' ? 'Extrator de ponto' : 'Sistema ponto'}</h1>
            <button onClick={onLogout} className="icon-button" aria-label="Sair da conta">
                <span className="material-symbols-outlined">account_circle</span>
            </button>
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
                        {extractorStep === 1 && (
                            <>
                                <div className="extractor-header">
                                    <h2>Selecione o modelo, o ficheiro e as páginas</h2>
                                    <input
                                        type="text"
                                        className="search-bar"
                                        placeholder="Pesquisar modelo... (ex: JBS)"
                                        value={searchTerm}
                                        onChange={(e) => setSearchTerm(e.target.value)}
                                    />
                                </div>
                                <div className="model-carousel-container">
                                    <div className="model-carousel">
                                        {Object.keys(modelNames)
                                            .filter(modelId => modelNames[modelId].toLowerCase().includes(searchTerm.toLowerCase()))
                                            .map(modelId => (
                                                <div
                                                    key={modelId}
                                                    className={`model-card ${modelType === modelId ? 'selected' : ''}`}
                                                    onClick={() => handleCardClick(modelId)}
                                                >
                                                    <img src={MODEL_IMAGE_PATHS[modelId]} alt={`Modelo ${modelNames[modelId]}`} />
                                                    <p>{modelNames[modelId]}</p>
                                                </div>
                                            ))}
                                    </div>
                                </div>
                                <div className="extractor-actions">
                                    <input type="file" accept=".pdf" ref={fileInputRef} onChange={handleFileSelect} style={{ display: 'none' }} />
                                    <button className="extractor-button" onClick={handleUploadClick}>
                                        {selectedFile ? `Ficheiro: ${selectedFile.name}` : 'Importar Ficheiro PDF'}
                                    </button>
                                    
                                    <input
                                        type="text" className="page-input" placeholder="Defina as páginas (ex: 1-10)"
                                        value={pageRange} onChange={(e) => setPageRange(e.target.value)}
                                    />

                                    <button
                                        className="advance-button"
                                        onClick={() => setExtractorStep(2)}
                                        disabled={!modelType || !selectedFile || !pageRange}
                                    >
                                        Avançar
                                    </button>
                                </div>
                            </>
                        )}
                        
                        {extractorStep === 2 && (
                            <>
                                <div className="extractor-header">
                                    <h2>Configurações</h2>
                                </div>
                                <div className="settings-container">
                                    <p className="settings-placeholder">Nenhuma configuração disponível no momento.</p>
                                </div>
                                <div className="extractor-actions">
                                    <button className="start-button" onClick={handleProcess} disabled={isProcessing}>
                                        {isProcessing ? 'A processar...' : 'iniciar e descarregar'}
                                    </button>
                                </div>
                            </>
                        )}
                    </div>
                )}
            </main>

            {zoomedModel && (
                <div className="zoom-overlay" onClick={() => setZoomedModel(null)}>
                    <div className="zoomed-card" onClick={(e) => e.stopPropagation()}>
                        <img src={MODEL_IMAGE_PATHS[zoomedModel]} alt={`Modelo ampliado ${modelNames[zoomedModel]}`} />
                        <p>{modelNames[zoomedModel]}</p>
                    </div>
                </div>
            )}

            {showProgressModal && (
                <ProgressModal
                    current={progressData.current_step} total={progressData.total_steps}
                    onClose={handleCloseModal} message={progressData.message}
                />
            )}
        </div>
    );
}

export default MainApp;


