import React from 'react';
import './ProgressModal.css';

const ProgressModal = ({ current, total, onClose, message, meta }) => {
  const isIndeterminate = total === 0;
  const percentage = !isIndeterminate ? Math.round((current / total) * 100) : 0;
  
  // ✨ Extrair informações extras do meta
  const uploadProgress = meta?.upload_progress || 0;
  const uploadTotal = meta?.upload_total || 0;
  const uploadMessage = meta?.upload_message || '';
  
  const downloadProgress = meta?.download_progress || 0;
  const downloadTotal = meta?.download_total || 0;
  const downloadMessage = meta?.download_message || '';
  
  const aiProcessing = meta?.ai_processing || false;
  const aiTotalPages = meta?.ai_total_pages || 0;
  const aiMessage = meta?.ai_message || '';
  
  const consolidating = meta?.consolidating || false;
  const cleanup = meta?.cleanup || false;
  
  // ✨ Determinar qual mensagem detalhada mostrar
  let detailedMessage = message;
  
  if (uploadTotal > 0 && uploadProgress < uploadTotal) {
    detailedMessage = uploadMessage;
  } else if (aiProcessing) {
    detailedMessage = aiMessage;
  } else if (downloadTotal > 0) {
    detailedMessage = downloadMessage;
  } else if (consolidating) {
    detailedMessage = "A consolidar dados na ordem cronológica...";
  } else if (cleanup) {
    detailedMessage = "A limpar arquivos temporários...";
  }
  
  return (
    <div className="progress-modal-overlay">
      <div className="progress-modal">
        <div className="progress-header">
          <h3>Processando PDF</h3>
          <button className="close-button" onClick={onClose} aria-label="Fechar">
            ×
          </button>
        </div>
        
        <div className="progress-content">
          <div className="progress-circle">
            <svg width="120" height="120" viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="50" fill="none" stroke="#e0e6ed" strokeWidth="8" />
              {!isIndeterminate && (
                <circle
                  cx="60"
                  cy="60"
                  r="50"
                  fill="none"
                  stroke="#28a745"
                  strokeWidth="8"
                  strokeLinecap="round"
                  strokeDasharray={`${2 * Math.PI * 50}`}
                  strokeDashoffset={`${2 * Math.PI * 50 * (1 - percentage / 100)}`}
                  transform="rotate(-90 60 60)"
                  style={{ transition: 'stroke-dashoffset 0.5s ease' }}
                />
              )}
            </svg>
            <div className="progress-text">
              <span className="percentage">{percentage}%</span>
            </div>
          </div>
          
          <div className="progress-info">
            <div className="page-counter">
              <span className="current-page">{isIndeterminate ? 0 : current}</span>
              <span className="separator">/</span>
              <span className="total-pages">{isIndeterminate ? '--' : total}</span>
              <span className="pages-label">etapas</span>
            </div>
            
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${percentage}%` }}
              ></div>
            </div>
            
            {/* ✨ Mensagem principal */}
            <div className="status-text">
              {detailedMessage}
            </div>
            
            {/* ✨ Detalhes adicionais de upload */}
            {uploadTotal > 0 && uploadProgress < uploadTotal && (
              <div className="status-detail">
                <div className="detail-bar-container">
                  <div className="detail-bar">
                    <div 
                      className="detail-bar-fill"
                      style={{ width: `${(uploadProgress / uploadTotal) * 100}%` }}
                    ></div>
                  </div>
                  <span className="detail-text">{uploadProgress}/{uploadTotal}</span>
                </div>
              </div>
            )}
            
            {/* ✨ Detalhes de processamento IA */}
            {aiProcessing && (
              <div className="status-detail ai-processing">
                <div className="spinner"></div>
                <span>Aguarde, a IA está a processar {aiTotalPages} páginas...</span>
              </div>
            )}
            
            {/* ✨ Detalhes adicionais de download */}
            {downloadTotal > 0 && downloadProgress > 0 && (
              <div className="status-detail">
                <div className="detail-bar-container">
                  <div className="detail-bar">
                    <div 
                      className="detail-bar-fill"
                      style={{ width: `${(downloadProgress / downloadTotal) * 100}%` }}
                    ></div>
                  </div>
                  <span className="detail-text">{downloadProgress}/{downloadTotal}</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProgressModal;

