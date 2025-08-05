import React, { useState, useRef } from 'react';
import './App.css';
import './style.css';
import Login from './Login';

const API_URLS = {
  '1': 'http://127.0.0.1:5000',
  '2': 'http://127.0.0.1:5001',
};

function App() {
  const [logado, setLogado] = useState(false);

  const [selectedFile, setSelectedFile] = useState(null);
  const [pageRange, setPageRange] = useState('');
  const [modelType, setModelType] = useState('1');
  const [statusMessage, setStatusMessage] = useState('Aguardando arquivo...');
  const [isProcessing, setIsProcessing] = useState(false);
  const [showModelOptions, setShowModelOptions] = useState(false);
  const [selectedModelImage, setSelectedModelImage] = useState('/modelo1.png');

  const fileInputRef = useRef(null);

  const handleLogin = () => {
    setLogado(true);
  };

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

    const apiUrl = `${API_URLS[modelType]}/process`;

    const formData = new FormData();
    formData.append('pdf_file', selectedFile);
    formData.append('pages', pageRange);

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

  if (!logado) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <div className="App">
      <header className="title">
        <h1>Extrator de Pontos</h1>
      </header>

      <main className="menu">

        <h2>1. Escolha o modelo do PDF</h2>
        <button
          className="buttonUpload"
          onClick={() => setShowModelOptions(!showModelOptions)}
        >
          Escolher modelo do PDF
        </button>

        {showModelOptions && (
          <div className="model-options">
            <label>
              <input
                type="radio"
                name="modelType"
                value="1"
                checked={modelType === '1'}
                onChange={(e) => {
                  setModelType(e.target.value);
                  setSelectedModelImage('/modelo1.png');
                }}
              />
              JBS Ponto (Padrão)
            </label>
            <label>
              <input
                type="radio"
                name="modelType"
                value="2"
                checked={modelType === '2'}
                onChange={(e) => {
                  setModelType(e.target.value);
                  setSelectedModelImage('/modelo2.png');
                }}
              />
              Cartão de Ponto (Modelo 2)
            </label>

            {selectedModelImage && (
              <div style={{ marginTop: '15px' }}>
                <img
                  src={selectedModelImage}
                  alt="Modelo selecionado"
                  style={{ width: '100%', maxWidth: '500px', borderRadius: '8px' }}
                />
              </div>
            )}
          </div>
        )}

        <h2>2. Escolha o arquivo PDF</h2>
        <input
          type="file"
          accept=".pdf"
          ref={fileInputRef}
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />
        <button className="buttonUpload" onClick={handleUploadClick}>
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

        <p id="status-message">{statusMessage}</p>
      </main>
    </div>
  );
}

export default App;
