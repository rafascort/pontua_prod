// /opt/pontua/AutoPonto/poupa-tempo/src/PeriodConfirmationModal.js
import React, { useState, useEffect } from 'react';

const formatDateInput = (value) => {
  let v = value.replace(/\D/g, '').slice(0, 8);
  if (v.length > 4) {
    v = `${v.slice(0, 2)}/${v.slice(2, 4)}/${v.slice(4)}`;
  } else if (v.length > 2) {
    v = `${v.slice(0, 2)}/${v.slice(2)}`;
  }
  return v;
};

const PeriodConfirmationModal = ({ pagesInfo, onConfirm, onCancel, isLoading }) => {
  const [periods, setPeriods] = useState([]);

  useEffect(() => {
    const initializedPeriods = pagesInfo.map(page => ({
      ...page,
      period: page.period || { start_date: '', end_date: '' }
    }));
    setPeriods(initializedPeriods);
  }, [pagesInfo]);

  const handleDateChange = (index, field, value) => {
    const formattedValue = formatDateInput(value);
    const newPeriods = [...periods];
    if (!newPeriods[index].period) {
      newPeriods[index].period = { start_date: '', end_date: '' };
    }
    newPeriods[index].period[field] = formattedValue;
    setPeriods(newPeriods);
  };

  const handleConfirm = () => {
    const validPeriods = periods.filter(p => {
        const dateRegex = /^\d{2}\/\d{2}\/\d{4}$/;
        return p.period && dateRegex.test(p.period.start_date) && dateRegex.test(p.period.end_date);
    });

    if(validPeriods.length === 0) {
        alert("Por favor, preencha o período completo (DD/MM/AAAA) para pelo menos uma página.");
        return;
    }
    onConfirm(validPeriods);
  };

  const handleApplyPattern = (startIndex) => {
    const seedPeriod = periods[startIndex]?.period;
    const dateRegex = /^\d{2}\/\d{2}\/\d{4}$/;

    if (!seedPeriod || !dateRegex.test(seedPeriod.start_date) || !dateRegex.test(seedPeriod.end_date)) {
      alert('Para aplicar o padrão, preencha o período completo (DD/MM/AAAA) da linha de origem.');
      return;
    }

    const parseDate = (dateString) => {
        const [day, month, year] = dateString.split('/');
        return new Date(parseInt(year), parseInt(month) - 1, parseInt(day));
    };

    const formatDate = (date) => {
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const year = date.getFullYear();
        return `${day}/${month}/${year}`;
    };

    // *** NOVA LÓGICA PARA DETECTAR FIM DE MÊS ***
    const isLastDayOfMonth = (date) => {
        const nextDay = new Date(date);
        nextDay.setDate(nextDay.getDate() + 1);
        return nextDay.getDate() === 1;
    };

    const newPeriods = [...periods];
    const seedStartDate = parseDate(seedPeriod.start_date);
    const seedEndDate = parseDate(seedPeriod.end_date);
    const seedEndWasLastDay = isLastDayOfMonth(seedEndDate);

    let lastStartDate = seedStartDate;
    let lastEndDate = seedEndDate;

    for (let i = startIndex + 1; i < newPeriods.length; i++) {
        lastStartDate.setMonth(lastStartDate.getMonth() + 1);
        
        if (seedEndWasLastDay) {
            // Se a data original era o fim do mês, calcula o novo fim de mês
            // Vai para o primeiro dia do mês seguinte ao próximo e volta um dia.
            lastEndDate = new Date(lastStartDate.getFullYear(), lastStartDate.getMonth() + 1, 0);
        } else {
            // Senão, apenas adiciona um mês
            lastEndDate.setMonth(lastEndDate.getMonth() + 1);
        }

        newPeriods[i].period = {
            start_date: formatDate(lastStartDate),
            end_date: formatDate(lastEndDate),
        };
    }

    setPeriods(newPeriods);
  };


  return (
    <div className="progress-modal-overlay">
      <div className="period-modal">
        <h3>Confirme os Períodos</h3>
        <p>Preencha uma linha e clique em "Aplicar" para preencher as demais em sequência.</p>
        
        <div className="period-list">
          {periods.map((page, index) => (
            <div key={page.page_number} className="period-item">
              <strong className="page-label">Página {page.page_number}:</strong>
              <input 
                type="text" 
                className="period-input" 
                value={page.period?.start_date || ''} 
                onChange={(e) => handleDateChange(index, 'start_date', e.target.value)}
                placeholder="DD/MM/AAAA"
                maxLength="10"
              />
              <span className="date-separator">a</span>
              <input 
                type="text" 
                className="period-input" 
                value={page.period?.end_date || ''} 
                onChange={(e) => handleDateChange(index, 'end_date', e.target.value)}
                placeholder="DD/MM/AAAA"
                maxLength="10"
              />
              <button 
                onClick={() => handleApplyPattern(index)} 
                className="apply-pattern-button"
                title="Preencher as datas abaixo a partir desta"
              >
                Aplicar
              </button>
            </div>
          ))}
        </div>

        <div className="period-actions">
          <button onClick={onCancel} className="extractor-button" disabled={isLoading}>Cancelar</button>
          <button onClick={handleConfirm} className="start-button" disabled={isLoading}>
            {isLoading ? 'Aguarde...' : 'Confirmar e Iniciar'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default PeriodConfirmationModal;
