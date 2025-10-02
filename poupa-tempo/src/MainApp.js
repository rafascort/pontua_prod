import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import ProgressModal from './ProgressModal';
import './App.css'; 

const API_BASE_URL = '/api';

// --- CAMINHOS E NOMES ATUALIZADOS (DEBUG REMOVIDO) ---
const MODEL_IMAGE_PATHS = {
    '1': process.env.PUBLIC_URL + '/Modelo1.png',
    '2': process.env.PUBLIC_URL + '/Modelo2.png',
    '3': process.env.PUBLIC_URL + '/Modelo3.png',
};

function MainApp({ onLogout, isAdmin }) {
    const navigate = useNavigate();
    const [view, setView] = useState('home');
    const [extractorStep, setExtractorStep] = useState(1);
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedFile, setSelectedFile] = useState(null);
    const [pageRange, setPageRange] = useState('');
    const [modelType, setModelType] = useState(null);
    const [zoomedModel, setZoomedModel] = useState(null);
    const [showProgressModal, setShowProgressModal] = useState(false);
    const [progressData, setProgressData] = useState({ current_step: 0, total_steps: 1, message: 'Iniciando...' });
    const fileInputRef = useRef(null);
    const progressIntervalRef = useRef(null);

    // ... (lógica de useEffect, reset, fileSelect, etc., permanecem as mesmas) ...
    useEffect(() => { Object.values(MODEL_IMAGE_PATHS).forEach(path => { if (path) new Image().src = path; }); }, []);
    useEffect(() => { return () => { if (progressIntervalRef.current) clearInterval(progressIntervalRef.current); }; }, []);
    const resetExtractorState = () => { setExtractorStep(1); setSearchTerm(''); setSelectedFile(null); setPageRange(''); setModelType(null); };
    const handleFileSelect = (event) => { const file = event.target.files[0]; if (file && file.type === 'application/pdf') setSelectedFile(file); else setSelectedFile(null); };
    const handleUploadClick = () => { fileInputRef.current.click(); };
    const handleCardClick = (modelId) => { setModelType(modelId); if (zoomedModel) setZoomedModel(null); };
    
    const checkProgress = async (taskId) => {
        const token = localStorage.getItem('jwt_token');
        if (!token) { onLogout(); return; }
        try {
            const response = await fetch(`${API_BASE_URL}/progress/${taskId}`, { headers: { 'Authorization': `Bearer ${token}` } });
            if (response.status === 401 || response.status === 403) { onLogout(); return; }
            if (!response.ok) throw new Error('Erro ao verificar progresso.');
            
            const data = await response.json();
            setProgressData({ current_step: data.current_step || 0, total_steps: data.total_steps || 1, message: data.message || 'A processar...' });
            
            if (data.status === 'completed' || data.status === 'error') {
                if (progressIntervalRef.current) { clearInterval(progressIntervalRef.current); progressIntervalRef.current = null; }
                if (data.status === 'completed' && data.file_path) {
                    const downloadResponse = await fetch(`${API_BASE_URL}/download/${taskId}`, { headers: { 'Authorization': `Bearer ${token}` } });
                    if (downloadResponse.ok) {
                        const blob = await downloadResponse.blob();
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a'); a.href = url; a.download = data.filename || 'resultado.csv'; document.body.appendChild(a); a.click(); a.remove(); window.URL.revokeObjectURL(url);
                    }
                }
                setTimeout(() => { setShowProgressModal(false); resetExtractorState(); }, 4000);
            }
        } catch (error) {
            console.error('Erro de rede:', error);
            if (progressIntervalRef.current) clearInterval(progressIntervalRef.current);
            setProgressData(prev => ({ ...prev, message: `Erro de rede: ${error.message}` }));
        }
    };

    const handleProcess = async () => {
        if (!selectedFile || !pageRange || !modelType) { alert('Complete todos os passos.'); return; }
        
        setShowProgressModal(true);
        setProgressData({ current_step: 0, total_steps: 1, message: 'A iniciar...' });
        
        const formData = new FormData();
        formData.append('pdf_file', selectedFile); formData.append('pages', pageRange); formData.append('model_type', modelType);
        
        const token = localStorage.getItem('jwt_token'); if (!token) { onLogout(); return; }
        
        try {
            const response = await fetch(`${API_BASE_URL}/process`, { method: 'POST', headers: { 'Authorization': `Bearer ${token}` }, body: formData });
            if (!response.ok) { const errorResult = await response.json(); if (response.status === 401 || response.status === 403) onLogout(); throw new Error(errorResult.error || errorResult.msg || 'Erro no servidor.'); }
            const result = await response.json();
            progressIntervalRef.current = setInterval(() => checkProgress(result.task_id), 2000);
        } catch (error) {
            console.error('Ocorreu um erro:', error);
            setProgressData({ current_step: 0, total_steps: 1, message: `Erro: ${error.message}` });
        }
    };

    const modelNames = { 
        '1': 'JBS Ponto', 
        '2': 'BRF Ponto', 
        '3': 'Ponto Mais',
    };

    const availableModels = Object.keys(modelNames)
        .filter(modelId => modelNames[modelId].toLowerCase().includes(searchTerm.toLowerCase()));

    const renderHeader = () => (
        <header className="top-bar">
            <button className="icon-button" onClick={() => { if (view === 'extractor') setView('home'); }}>
                <span className="material-symbols-outlined">{view === 'extractor' ? 'arrow_back' : 'menu'}</span>
            </button>
            <h1 className="title">{view === 'extractor' ? 'Extrator de ponto' : 'Sistema Ponto'}</h1>
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
                            <input type="text" className="search-bar" placeholder="Pesquisar modelo..." value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} />
                        </div>
                        <div className="model-carousel-container">
                            <div className="model-carousel">
                                {availableModels.map(modelId => (
                                    <div key={modelId} className={`model-card ${modelType === modelId ? 'selected' : ''}`} onClick={() => handleCardClick(modelId)}>
                                        <img src={MODEL_IMAGE_PATHS[modelId]} alt={`Modelo ${modelNames[modelId]}`} />
                                        <p>{modelNames[modelId]}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div className="extractor-actions">
                            <input type="file" accept=".pdf" ref={fileInputRef} onChange={handleFileSelect} style={{ display: 'none' }} />
                            <button className="extractor-button" onClick={handleUploadClick}>{selectedFile ? `Ficheiro: ${selectedFile.name}` : 'Importar Ficheiro PDF'}</button>
                            <input type="text" className="page-input" placeholder="Defina as páginas (ex: 1-10)" value={pageRange} onChange={(e) => setPageRange(e.target.value)} />
                            <button className="start-button" onClick={handleProcess} disabled={!modelType || !selectedFile || !pageRange || (showProgressModal && progressData.message.includes('processar'))}>
                                { (showProgressModal && progressData.message.includes('processar')) ? 'A processar...' : 'Iniciar e Descarregar'}
                            </button>
                        </div>
                    </div>
                )}
            </main>

            {showProgressModal && (
                <ProgressModal current={progressData.current_step} total={progressData.total_steps} onClose={() => setShowProgressModal(false)} message={progressData.message} />
            )}
        </div>
    );
}

export default MainApp;
