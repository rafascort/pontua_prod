// funcionaaaa
// src/App.js
import React, { useState, useRef } from 'react';
import './App.css'; // Importa nosso CSS

// A URL da nossa API Flask.
const API_URL = 'http://127.0.0.1:5000';

function App() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [pageRange, setPageRange] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  
  // Ref para o input de arquivo escondido
  const fileInputRef = useRef(null);

  const handleFileSelect = (event) => {
    const file = event.target.files[0];
    if (file && file.type === 'application/pdf') {
      setSelectedFile(file);
      setStatusMessage(`Arquivo selecionado: ${file.name}`);
      setUploadSuccess(false); // Reseta o status de sucesso ao selecionar novo arquivo
    } else {
      setSelectedFile(null);
      setStatusMessage('Por favor, selecione um arquivo PDF.');
    }
  };
  
  const handleUploadClick = () => {
    // Abre o explorador de arquivos ao clicar no botão
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
    setStatusMessage('Enviando e processando o arquivo...');

    const formData = new FormData();
    formData.append('pdf_file', selectedFile);

    try {
      // 1. Faz o upload do arquivo
      const uploadResponse = await fetch(`${API_URL}/upload`, {
        method: 'POST',
        body: formData,
      });

      const uploadResult = await uploadResponse.json();
      if (!uploadResult.success) {
        throw new Error(`Erro no Upload: ${uploadResult.message}`);
      }
      
      setStatusMessage('Upload concluído. Iniciando processamento...');
      
      // 2. Inicia o processamento
      const processResponse = await fetch(`${API_URL}/process`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: uploadResult.filename,
          pages: pageRange,
        }),
      });

      const processResult = await processResponse.json();
      if (!processResult.success) {
        throw new Error(`Erro no Processamento: ${processResult.message}`);
      }

      // 3. Sucesso! Mostra o pop-up e aciona o download
      alert('Processo finalizado com sucesso!');
      window.location.href = `${API_URL}/download/${processResult.download_filename}`;
      
      setStatusMessage(`Download do arquivo ${processResult.download_filename} iniciado.`);
      setUploadSuccess(true); // Marca que o processo foi um sucesso

    } catch (error) {
      console.error('Ocorreu um erro:', error);
      setStatusMessage(error.message);
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
        <h2>1. Escolha o arquivo PDF</h2>
        {/* Input de arquivo escondido, controlado pelo Ref */}
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

        <h2>2. Defina as páginas</h2>
        <input
          type="text"
          className="pageInput"
          placeholder="Ex: 0-20"
          value={pageRange}
          onChange={(e) => setPageRange(e.target.value)}
        />
        
        <h2>3. Inicie o processo</h2>
        <button
          className="buttonStart"
          onClick={handleProcess}
          disabled={!selectedFile || !pageRange || isProcessing}
        >
          {isProcessing ? 'Processando...' : 'INICIAR'}
        </button>
        
        <p id="status-message" style={{ color: uploadSuccess ? 'green' : 'red' }}>
          {statusMessage}
        </p>
      </main>
    </div>
  );
}

export default App;