// src/ProgressModal.js
import React from 'react';
import './ProgressModal.css';

const ProgressModal = ({ current, total, onClose }) => {
  const percentage = total > 0 ? Math.round((current / total) * 100) : 0;
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
              <circle
                cx="60"
                cy="60"
                r="50"
                fill="none"
                stroke="#e0e6ed"
                strokeWidth="8"
              />
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
            </svg>
            <div className="progress-text">
              <span className="percentage">{percentage}%</span>
            </div>
          </div>
          <div className="progress-info">
            <div className="page-counter">
              <span className="current-page">{current}</span>
              <span className="separator">/</span>
              <span className="total-pages">{total}</span>
              <span className="pages-label">páginas</span> {/* ALTERADO AQUI: "etapas" para "páginas" */}
            </div>
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${percentage}%` }}
              ></div>
            </div>
            <div className="status-text">
              {current === 0 && total === 0 ? 'Iniciando...' :
               current === total && total > 0 ? 'Finalizando...' :
               `Processando página ${current} de ${total}`} {/* ALTERADO AQUI: "Executando etapa" para "Processando página" */}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProgressModal;
