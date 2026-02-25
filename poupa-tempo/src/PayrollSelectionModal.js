import React, { useState } from 'react';
import { fetchWithAuth } from './apiUtils';
import { toast } from 'react-toastify';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faCheckCircle, faTimes, faPlay } from '@fortawesome/free-solid-svg-icons';

const PayrollSelectionModal = ({ data, onClose, onConfirm }) => {
    // Inicializa com todas as verbas marcadas por padrão
    const [selectedVerbas, setSelectedVerbas] = useState(data.verbas || []);

    const toggleVerba = (verba) => {
        if (selectedVerbas.includes(verba)) {
            setSelectedVerbas(selectedVerbas.filter(v => v !== verba));
        } else {
            setSelectedVerbas([...selectedVerbas, verba]);
        }
    };

    const handleStartProcessing = async () => {
        if (selectedVerbas.length === 0) {
            return toast.warn("Selecione pelo menos uma verba para processar.");
        }

        try {
            const response = await fetchWithAuth('/api/payroll/process', {
                method: 'POST',
                body: JSON.stringify({
                    pdf_path: data.pdf_path,
                    pages: data.pages,
                    selected_verbas: selectedVerbas
                })
            });

	    const resData = await response.json(); // Pegamos o JSON da resposta

        if (response.ok && resData.task_id) {
            toast.success("Processamento iniciado!");
            onConfirm(resData.task_id); // PASSE O TASK_ID AQUI
        } else {
            toast.error(resData.error || "Erro ao iniciar.");
        }
    } catch (error) {
        toast.error("Erro na comunicação.");
    }
};

    return (
        <div className="progress-modal-overlay">
            <div className="period-modal" style={{ maxWidth: '700px', width: '90%' }}>
                <div className="modal-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                    <h3>Configuração da Extração</h3>
                    <button className="close-button" onClick={onClose} style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', fontSize: '20px' }}>
                        <FontAwesomeIcon icon={faTimes} />
                    </button>
                </div>

                <div className="modal-body">
                    <div className="info-section" style={{ marginBottom: '20px', padding: '15px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
                        <p><strong>Funcionários Detectados:</strong> {data.nomes && data.nomes.length > 0 ? data.nomes.join(', ') : 'Nenhum nome identificado no pre-scan'}</p>
                        <p><strong>Intervalo de Páginas:</strong> {data.pages}</p>
                    </div>

                    <h4 style={{ marginBottom: '15px' }}>Selecione as Verbas/Itens (Checkboxes):</h4>
                    <div className="verbas-selection-grid" style={{ 
                        display: 'grid', 
                        gridTemplateColumns: '1fr 1fr', 
                        gap: '12px', 
                        maxHeight: '350px', 
                        overflowY: 'auto', 
                        padding: '10px',
                        background: '#1a1a1a',
                        borderRadius: '8px'
                    }}>
                        {data.verbas && data.verbas.map((verba, index) => (
                            <label key={index} style={{ 
                                display: 'flex', 
                                alignItems: 'center', 
                                cursor: 'pointer',
                                padding: '8px',
                                borderRadius: '4px',
                                background: selectedVerbas.includes(verba) ? 'rgba(52, 152, 219, 0.2)' : 'transparent',
                                border: '1px solid',
                                borderColor: selectedVerbas.includes(verba) ? '#3498db' : 'rgba(255,255,255,0.1)'
                            }}>
                                <input 
                                    type="checkbox" 
                                    checked={selectedVerbas.includes(verba)} 
                                    onChange={() => toggleVerba(verba)}
                                    style={{ marginRight: '12px', width: '18px', height: '18px' }}
                                />
                                <span style={{ fontSize: '14px', color: '#ecf0f1' }}>{verba}</span>
                            </label>
                        ))}
                    </div>
                </div>

                <div className="period-actions" style={{ marginTop: '25px', display: 'flex', gap: '15px', justifyContent: 'flex-end' }}>
                    <button onClick={onClose} className="extractor-button" style={{ background: '#7f8c8d' }}>
                        Cancelar
                    </button>
                    <button onClick={handleStartProcessing} className="start-button">
                        <FontAwesomeIcon icon={faPlay} /> Confirmar e Gerar CSV
                    </button>
                </div>
            </div>
        </div>
    );
};

export default PayrollSelectionModal;
