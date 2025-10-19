// /opt/pontua/AutoPonto/poupa-tempo/src/MainApp.js
import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import ProgressModal from './ProgressModal';
import PeriodConfirmationModal from './PeriodConfirmationModal';
import './App.css';
import './ProgressModal.css';
import './PeriodConfirmationModal.css';

const API_BASE_URL = '/api';

const MODEL_IMAGE_PATHS = {
    '1': process.env.PUBLIC_URL + '/Modelo1.png',
    '6': process.env.PUBLIC_URL + '/Modelo_IA_Geral.png',
    '7': process.env.PUBLIC_URL + '/Modelo_IA_Geral.png',
};

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

    useEffect(() => {
        Object.values(MODEL_IMAGE_PATHS).forEach(path => {
            if (path) new Image().src = path;
        });
    }, []);

    useEffect(() => {
        return () => {
            if (progressIntervalRef.current) {
                clearInterval(progressIntervalRef.current);
            }
        };
    }, []);

    const resetExtractorState = () => {
        setModelType(null);
        setSelectedFile(null);
        setPageRange('');
        setSearchTerm('');
        setIsLoading(false);
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    const handleFileSelect = (event) => {
        const file = event.target.files[0];
        if (file && file.type === 'application/pdf') {
            setSelectedFile(file);
        } else {
            setSelectedFile(null);
        }
    };

    const handleUploadClick = () => {
        fileInputRef.current.click();
    };

    const handleCardClick = (modelId) => {
        setModelType(modelId);
    };

    const checkFullProgress = async (taskId) => {
        const token = localStorage.getItem('jwt_token');
        if (!token) {
            onLogout();
            return;
        }
        try {
            const response = await fetch(`${API_BASE_URL}/progress/${taskId}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (!response.ok) {
                throw new Error('Erro ao verificar progresso.');
            }
            const data = await response.json();
            setProgressData(data);

            if (data.status === 'completed' || data.status === 'error') {
                clearInterval(progressIntervalRef.current);
                progressIntervalRef.current = null;
                setIsLoading(false);

                if (data.status === 'completed' && data.file_path) {
                    const downloadResponse = await fetch(`${API_BASE_URL}/download/${taskId}`, {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    if (downloadResponse.ok) {
                        const blob = await downloadResponse.blob();
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = data.filename || 'resultado.csv';
                        document.body.appendChild(a);
                        a.click();
                        a.remove();
                        window.URL.revokeObjectURL(url);
                    }
                }
                setTimeout(() => {
                    setShowProgressModal(false);
                    resetExtractorState();
                }, 5000);
            }
        } catch (error) {
            setProgressData(prev => ({ ...prev, message: `Erro de rede: ${error.message}`, status: 'error' }));
            setIsLoading(false);
            if (progressIntervalRef.current) { // Verifica se ainda existe antes de limpar
               clearInterval(progressIntervalRef.current);
               progressIntervalRef.current = null; // Garante que a referência é limpa
            }
        }
    };

    const checkPeriodExtractionProgress = async (taskId) => {
        const token = localStorage.getItem('jwt_token');
        try {
            const response = await fetch(`${API_BASE_URL}/progress/${taskId}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            const data = await response.json();
            setProgressData(data);

            if (data.status === 'completed') {
                clearInterval(progressIntervalRef.current);
                progressIntervalRef.current = null; // Limpa referência
                setShowProgressModal(false);
                setPagesInfo(data.result);
                setInitialPdfPath(data.pdf_path);
                setShowPeriodModal(true);
                setIsLoading(false);
            } else if (data.status === 'error') {
                clearInterval(progressIntervalRef.current);
                progressIntervalRef.current = null; // Limpa referência
                setIsLoading(false);
                setTimeout(() => {
                    setShowProgressModal(false);
                    resetExtractorState();
                }, 5000);
            }
        } catch (error) {
            setProgressData(prev => ({ ...prev, message: `Erro de rede: ${error.message}`, status: 'error' }));
            setIsLoading(false);
             if (progressIntervalRef.current) { // Verifica se ainda existe antes de limpar
               clearInterval(progressIntervalRef.current);
               progressIntervalRef.current = null; // Garante que a referência é limpa
            }
        }
    };

    const handleStartProcess = () => {
        if (!modelType) {
             alert('Por favor, selecione um modelo.');
             return;
        }
        if (!selectedFile) {
             alert('Por favor, importe um ficheiro PDF.');
             return;
        }
        if (!pageRange && (modelType !== '7')) { // Apenas modelos não-diretos exigem páginas inicialmente
             alert('Por favor, defina as páginas a serem processadas.');
             return;
        }

        if (modelType === '7') {
            handleDirectProcess();
        } else {
            handleInitialProcess();
        }
    };

    const handleDirectProcess = async () => {
        // Redundante, mas mantém por segurança
        if (!selectedFile || !modelType) {
            alert('Por favor, selecione o modelo e o arquivo.');
            return;
        }

        setIsLoading(true);
        setShowProgressModal(true);
        setProgressData({ current_step: 0, total_steps: 3, message: 'Enviando para processamento...' });

        const formData = new FormData();
        formData.append('pdf_file', selectedFile);
        formData.append('pages', pageRange); // Envia mesmo se vazio, backend lida
        formData.append('model_type', modelType);

        const token = localStorage.getItem('jwt_token');
        if (!token) {
            onLogout();
            return;
        }

        try {
            const response = await fetch(`${API_BASE_URL}/process-direct`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData,
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Falha ao iniciar o processamento.');
            }

            const result = await response.json();
             if (progressIntervalRef.current) clearInterval(progressIntervalRef.current); // Limpa anterior
            progressIntervalRef.current = setInterval(() => checkFullProgress(result.task_id), 3000);
        } catch (error) {
            setProgressData({ current_step: 3, total_steps: 3, message: `Erro: ${error.message}`, status: 'error' });
            setTimeout(() => {
                setShowProgressModal(false);
                setIsLoading(false);
                resetExtractorState();
            }, 5000);
        }
    };

    const handleInitialProcess = async () => {
         // Redundante, mas mantém por segurança
        if (!selectedFile || !pageRange || !modelType) {
            alert('Por favor, selecione o modelo, o arquivo e as páginas.');
            return;
        }

        setIsLoading(true);
        setShowProgressModal(true);
        setProgressData({ current_step: 0, total_steps: 1, message: 'Lendo os períodos do PDF...' });

        const formData = new FormData();
        formData.append('pdf_file', selectedFile);
        formData.append('pages', pageRange);

        const token = localStorage.getItem('jwt_token');
        if (!token) {
            onLogout();
            return;
        }

        try {
            const response = await fetch(`${API_BASE_URL}/extract-periods`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData,
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Falha ao iniciar extração de períodos.');
            }

            const result = await response.json();
             if (progressIntervalRef.current) clearInterval(progressIntervalRef.current); // Limpa anterior
            progressIntervalRef.current = setInterval(() => checkPeriodExtractionProgress(result.task_id), 1500);
        } catch (error) {
            setProgressData({ current_step: 1, total_steps: 1, message: `Erro: ${error.message}`, status: 'error' });
            setTimeout(() => {
                setShowProgressModal(false);
                setIsLoading(false);
                resetExtractorState();
            }, 5000);
        }
    };

    const handleConfirmAndProcess = async (confirmedPeriods) => {
        setShowPeriodModal(false);
        setIsLoading(true);
        setShowProgressModal(true);
        setProgressData({ current_step: 0, total_steps: 3, message: 'Enviando para processamento com IA...' });

        const token = localStorage.getItem('jwt_token');
        if (!token) {
            onLogout();
            return;
        }

        try {
            const response = await fetch(`${API_BASE_URL}/process`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    pdf_path: initialPdfPath,
                    pages_with_periods: confirmedPeriods,
                    model_type: modelType,
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Falha ao iniciar processamento completo.');
            }

            const result = await response.json();
             if (progressIntervalRef.current) clearInterval(progressIntervalRef.current); // Limpa anterior
            progressIntervalRef.current = setInterval(() => checkFullProgress(result.task_id), 3000);
        } catch (error) {
            setProgressData({ current_step: 3, total_steps: 3, message: `Erro: ${error.message}`, status: 'error' });
            setTimeout(() => {
                setShowProgressModal(false);
                setIsLoading(false);
                resetExtractorState();
            }, 5000);
        }
    };

    const modelNames = {
        '1': 'JBS Ponto',
        '6': 'Modelo sem DD/MM/AAAA',
        '7': 'Modelo com DD/MM/AAAA',
    };

    const availableModels = Object.keys(modelNames).filter(modelId => {
        // Removido filtro de debug, já que não está em modelNames
        return modelNames[modelId].toLowerCase().includes(searchTerm.toLowerCase());
    });

    const renderHeader = () => (
        <header className="top-bar">
            {/* Botão com lógica e ícone fixo */}
            <button
                className="icon-button"
                onClick={() => {
                    // Sempre volta para 'home' e limpa o estado do extrator
                    setView('home');
                    resetExtractorState();
                }}
                title="Voltar ao início" // Título fixo
            >
                {/* Ícone sempre 'home' */}
                <span className="material-symbols-outlined">home</span>
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
                                                <span className="material-symbols-outlined" style={{ fontSize: '60px', color: '#ecf0f1' }}>smart_toy</span>
                                            </div>
                                        )}
                                        <p>{modelNames[modelId]}</p>
                                    </div>
                                ))}
                                {/* Adiciona um aviso se a pesquisa não retornar resultados */}
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
                            <button className="extractor-button" onClick={handleUploadClick}>
                                {selectedFile ? `Ficheiro: ${selectedFile.name}` : 'Importar Ficheiro PDF'}
                            </button>
                            <input
                                type="text"
                                className="page-input"
                                placeholder="Páginas (ex: 1-5, 8, 10-12)" // Placeholder atualizado
                                value={pageRange}
                                onChange={(e) => setPageRange(e.target.value)}
                                // Desabilita se for modelo 7 e nenhum arquivo selecionado
                                disabled={modelType === '7' && !selectedFile}
                            />
                            <button className="start-button" onClick={handleStartProcess} disabled={isLoading || !modelType || !selectedFile || (!pageRange && modelType !== '7')}>
                                {isLoading ? 'Aguarde...' : 'Iniciar'}
                            </button>
                        </div>
                    </div>
                )}
            </main>
            {showProgressModal && <ProgressModal {...progressData} onClose={() => {
                 setShowProgressModal(false);
                 // Adicional: Se o processo terminou (com sucesso ou erro), reseta o estado
                 if (progressData.status === 'completed' || progressData.status === 'error') {
                    resetExtractorState();
                 }
                 // Cancela o polling se o modal for fechado manualmente durante o processamento
                 if (progressIntervalRef.current) {
                    clearInterval(progressIntervalRef.current);
                    progressIntervalRef.current = null;
                 }
                 // Reset isLoading se fechar manualmente durante o loading inicial
                 if (isLoading) setIsLoading(false);
            }} />}
            {showPeriodModal && <PeriodConfirmationModal pagesInfo={pagesInfo} onConfirm={handleConfirmAndProcess} onCancel={() => { setShowPeriodModal(false); resetExtractorState(); }} isLoading={isLoading} />}
        </div>
    );
}

export default MainApp;
