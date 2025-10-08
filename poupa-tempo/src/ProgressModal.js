import React from 'react';
import './ProgressModal.css';

// A assinatura foi corrigida para refletir os dados recebidos do backend
const ProgressModal = ({ current_step, total_steps, onClose, message, status, ...meta }) => {
  
  // --- Lógica aprimorada para determinar o que exibir ---
  
  // Informações dos sub-passos vêm do objeto 'meta'
  const { 
    ai_processing, 
    ai_current_page, 
    ai_total_pages, 
    ai_message,
    upload_progress,
    upload_total,
    upload_message,
    download_progress,
    download_total,
    download_message
  } = meta;

  // Variáveis padrão, baseadas nas etapas gerais (ex: 1 de 3)
  let displayCurrent = current_step;
  let displayTotal = total_steps;
  let displayLabel = 'etapas';
  let detailedMessage = message;

  // Se uma sub-etapa (como a da IA) estiver ativa, suas informações de progresso terão prioridade
  if (ai_processing && ai_total_pages > 0) {
    displayCurrent = ai_current_page || 0;
    displayTotal = ai_total_pages;
    displayLabel = 'páginas';
    detailedMessage = ai_message || `A processar ${displayCurrent} de ${displayTotal} pela IA...`;
  } else if (upload_total > 0 && current_step === 0) {
    displayCurrent = upload_progress || 0;
    displayTotal = upload_total;
    displayLabel = 'páginas';
    detailedMessage = upload_message || `Subindo ${displayCurrent} de ${displayTotal} páginas...`;
  } else if (download_total > 0 && current_step === 2) {
    displayCurrent = download_progress || 0;
    displayTotal = download_total;
    displayLabel = 'resultados';
    detailedMessage = download_message || `Baixando ${displayCurrent} de ${displayTotal} resultados...`;
  }
  
  // Calcula a porcentagem com base nos valores corretos, evitando divisão por zero
  const isIndeterminate = !displayTotal || displayTotal === 0;
  const percentage = !isIndeterminate ? Math.round((displayCurrent / displayTotal) * 100) : 0;
  
  return (
    <div className="progress-modal-overlay">
      <div className="progress-modal">
        <div className="progress-header">
          <h3>Processando PDF</h3>
          {status !== 'processing' && (
            <button className="close-button" onClick={onClose} aria-label="Fechar">
              ×
            </button>
          )}
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
                  strokeDashoffset={`${2 * Math.PI * 50 * (1 - (percentage / 100))}`}
                  transform="rotate(-90 60 60)"
                  style={{ transition: 'stroke-dashoffset 0.5s ease' }}
                />
              )}
            </svg>
            <div className="progress-text">
              <span className="percentage">{isIndeterminate ? '0%' : `${percentage}%`}</span>
            </div>
          </div>
          
          <div className="progress-info">
            <div className="page-counter">
              <span className="current-page">{isIndeterminate ? '' : displayCurrent}</span>
              <span className="separator">/</span>
              <span className="total-pages">{isIndeterminate ? '' : displayTotal}</span>
              <span className="pages-label">{isIndeterminate ? 'Aguarde...' : displayLabel}</span>
            </div>
            
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${percentage}%` }}
              ></div>
            </div>
            
            <div className="status-text">
              {detailedMessage}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProgressModal;
