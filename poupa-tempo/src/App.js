// src/App.js
import React, { useState, useRef } from 'react';
import './App.css'; // Importa nosso CSS

// Mapeamento dos nossos servidores de API
const API_URLS = {
  '1': 'http://127.0.0.1:5000', // URL para o app_modelo1.py
  '2': 'http://127.0.0.1:5001', // URL para o app_modelo2.py
};

function App() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [pageRange, setPageRange] = useState('');
  const [modelType, setModelType] = useState('1'); // Começa com o Modelo 1 selecionado
  const [statusMessage, setStatusMessage] = useState('Aguardando arquivo...');
  const [isProcessing, setIsProcessing] = useState(false);
  
  const fileInputRef = useRef(null);

  const handleFileSelect = (event) => {
    const file = event.target.files[0];
    if (file && file.type === 'application/pdf') {
      setSelectedFile(file);
      setStatusMessage(`Arquivo selecionado: ${file.name}`);
    } else {
      setSelectedFile(null);
      setStatusMessage('Por favor, selecione um arquivo PDF.');
    }
  };
  
  const handleUploadClick = () => {
    fileInputRef.current.click();
  };

  const handleProcess = async () => {
    if (!selectedFile) {
      alert('Por favor, selecione um arquivo primeiro.');
      return;
    }
    if (!pageRange) {
        alert('Por favor, informe o intervalo de páginas.');
        return;
    }

    setIsProcessing(true);
    setStatusMessage('Enviando e processando o arquivo... Isso pode levar um momento.');

    // Seleciona a URL correta com base no modelo escolhido
    const apiUrl = `${API_URLS[modelType]}/process`;
    console.log(`Enviando requisição para: ${apiUrl}`); // Log para debug

    const formData = new FormData();
    formData.append('pdf_file', selectedFile);
    formData.append('pages', pageRange);
    // Não precisamos mais enviar 'model_type', pois cada servidor só lida com um tipo.

    try {
      const response = await fetch(apiUrl, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorResult = await response.json();
        throw new Error(errorResult.message || 'Ocorreu um erro no servidor.');
      }

      const blob = await response.blob();
      
      const contentDisposition = response.headers.get('Content-Disposition');
      let filename = 'resultado.csv';
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="(.+)"/);
        if (filenameMatch && filenameMatch.length > 1) {
          filename = filenameMatch[1];
        }
      }
      
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);

      setStatusMessage(`Processo finalizado! O download de '${filename}' foi iniciado.`);

    } catch (error) {
      console.error('Ocorreu um erro:', error);
      setStatusMessage(`Erro: ${error.message}`);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="App">
      <header className="title">
        <h1>Extrator de Pontos</h1>
      </header>

      <main className="menu">
        <h2>1. Escolha o modelo do PDF</h2>
        <select 
          className="modelSelect"
          value={modelType}
          onChange={(e) => setModelType(e.target.value)}
        >
          <option value="1">JBS Ponto (Padrão)</option>
          <option value="2">Cartão de Ponto (Modelo 2)</option>
          {/* Adicione mais <option> aqui para futuros modelos */}
        </select>

        <h2>2. Escolha o arquivo PDF</h2>
        <input
          type="file"
          accept=".pdf"
          ref={fileInputRef}
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />
        <button 
          className="buttonUpload" 
          onClick={handleUploadClick}>
          Procurar Arquivo PDF
        </button>

        <h2>3. Defina as páginas</h2>
        <input
          type="text"
          className="pageInput"
          placeholder="Ex: 216-272"
          value={pageRange}
          onChange={(e) => setPageRange(e.target.value)}
        />
        
        <h2>4. Inicie o processo</h2>
        <button
          className="buttonStart"
          onClick={handleProcess}
          disabled={!selectedFile || !pageRange || isProcessing}
        >
          {isProcessing ? 'Processando...' : 'INICIAR E BAIXAR'}
        </button>
        
        <p id="status-message">
          {statusMessage}
        </p>
      </main>
    </div>
  );
}

export default App;
