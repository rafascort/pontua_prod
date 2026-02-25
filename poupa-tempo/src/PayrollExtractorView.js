import React, { useState, useRef } from 'react';
import { fetchWithAuth } from './apiUtils';
import { toast } from 'react-toastify';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faUpload, faSync, faArrowLeft, faSpinner } from '@fortawesome/free-solid-svg-icons';
import PayrollSelectionModal from './PayrollSelectionModal';

const PayrollExtractorView = ({ onBack }) => {
    const [selectedFile, setSelectedFile] = useState(null);
    const [pageRange, setPageRange] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [isProcessingFinal, setIsProcessingFinal] = useState(false);
    const [analysisData, setAnalysisData] = useState(null);
    const [showModal, setShowModal] = useState(false);
    const [progress, setProgress] = useState({ current: 0, total: 1, message: '' });
    const fileInputRef = useRef(null);

    const handleDownload = async (taskId) => {
        try {
            const response = await fetchWithAuth(`/api/download/${taskId}`);
            if (!response.ok) throw new Error();
            
            const blob = await response.blob();
            // Garantir o tipo MIME correto para Excel .xlsx
            const excelBlob = new Blob([blob], { 
                type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' 
            });
            
            const url = window.URL.createObjectURL(excelBlob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `Folha_Extraida_${taskId}.xlsx`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            toast.success("Excel transferido com sucesso!");
        } catch (e) {
            toast.error("Erro ao transferir o ficheiro Excel.");
        }
    };

    const monitorFinalProgress = (taskId) => {
        setIsProcessingFinal(true);
        const interval = setInterval(async () => {
            try {
                const res = await fetchWithAuth(`/api/progress/${taskId}`);
                const data = await res.json();

                if (data.current_step) {
                    setProgress({ current: data.current_step, total: data.total_steps, message: data.message });
                }

                if (data.status === 'completed' || data.status === 'finished') {
                    clearInterval(interval);
                    setIsProcessingFinal(false);
                    await handleDownload(taskId);
                } else if (data.status === 'error' || data.status === 'failed') {
                    clearInterval(interval);
                    setIsProcessingFinal(false);
                    toast.error("Erro no processamento.");
                }
            } catch (e) { clearInterval(interval); }
        }, 2000);
    };

    const handleStartAnalysis = async () => {
        if (!selectedFile || !pageRange) return toast.warn("Preencha todos os campos.");
        setIsLoading(true);
        const formData = new FormData();
        formData.append('pdf_file', selectedFile);
        formData.append('pages', pageRange);

        try {
            const response = await fetchWithAuth('/api/payroll/analyze', { method: 'POST', body: formData });
            const data = await response.json();
            if (data.task_id) {
                const interval = setInterval(async () => {
                    const res = await fetchWithAuth(`/api/progress/${data.task_id}`);
                    const d = await res.json();
                    if (d.status === 'completed') {
                        clearInterval(interval);
                        setAnalysisData(d.result);
                        setShowModal(true);
                        setIsLoading(false);
                    }
                }, 2000);
            }
        } catch (e) { setIsLoading(false); }
    };

    return (
        <div className="extractor-container">
            <div className="extractor-header">
                <button className="back-button" onClick={onBack}><FontAwesomeIcon icon={faArrowLeft} /> Voltar</button>
                <h2>Extração de Folha de Pagamento</h2>
            </div>

            <div className="extractor-actions">
                <input type="file" accept=".pdf" ref={fileInputRef} style={{ display: 'none' }} onChange={(e) => setSelectedFile(e.target.files[0])} />
                <button className="extractor-button" onClick={() => fileInputRef.current.click()} disabled={isLoading || isProcessingFinal}>
                    <FontAwesomeIcon icon={faUpload} /> {selectedFile ? selectedFile.name.substring(0, 20) : 'Importar PDF'}
                </button>
                <input type="text" className="page-input" placeholder="Ex: 1-10" value={pageRange} onChange={(e) => setPageRange(e.target.value)} disabled={isLoading || isProcessingFinal} />
                <button className="start-button" onClick={handleStartAnalysis} disabled={isLoading || isProcessingFinal || !selectedFile || !pageRange}>
                    <FontAwesomeIcon icon={isLoading ? faSpinner : faSync} spin={isLoading} /> {isLoading ? ' Analisar' : ' Identificar Itens'}
                </button>
            </div>

            {showModal && analysisData && (
                <PayrollSelectionModal 
                    data={analysisData} 
                    onClose={() => setShowModal(false)} 
                    onConfirm={(taskId) => { setShowModal(false); monitorFinalProgress(taskId); }} 
                />
            )}

            {isProcessingFinal && (
                <div className="progress-modal-overlay">
                    <div className="progress-modal" style={{ textAlign: 'center', padding: '40px', maxWidth: '500px' }}>
                        <h3>A processar Folha</h3>
                        <FontAwesomeIcon icon={faSpinner} spin size="3x" style={{ color: '#3498db', margin: '20px 0' }} />
                        <div style={{ background: '#2c3e50', borderRadius: '10px', height: '25px', overflow: 'hidden' }}>
                            <div style={{ width: `${(progress.current / progress.total) * 100}%`, background: '#2ecc71', height: '100%', transition: 'width 0.4s ease' }}></div>
                        </div>
                        <p>Página {progress.current} de {progress.total}</p>
                    </div>
                </div>
            )}
        </div>
    );
};

export default PayrollExtractorView;
