import React, { useState, useRef, useEffect } from 'react';
import './App.css';
import Login from './Login';
import ProgressModal from './ProgressModal'; // Importar seu modal

const API_URLS = {
  '1': 'http://127.0.0.1:5000',
  '2': 'http://127.0.0.1:5001',
  'teste': 'http://127.0.0.1:5002',
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

  // Estados para o modal de progresso
  const [showProgressModal, setShowProgressModal] = useState(false);
  const [currentTaskId, setCurrentTaskId] = useState(null);
  const [progressData, setProgressData] = useState({
    current_step: 0,
    total_steps: 10,
    progress: 0,
    message: 'Iniciando...'
  });

  const fileInputRef = useRef(null);
  const progressIntervalRef = useRef(null);

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

  const checkProgress = async (taskId) => {
    try {
      const response = await fetch(`${API_URLS[modelType]}/progress/${taskId}`);

      if (response.ok) {
        const data = await response.json();

        // Atualizar dados do progresso
        setProgressData({
          current_step: data.current_step || 0,
          total_steps: data.total_steps || 10,
          progress: data.progress || 0,
          message: data.message || 'Processando...'
        });

        setStatusMessage(data.message || 'Processando...');

        if (data.status === 'completed') {
          // Download automático
          const downloadUrl = `${API_URLS[modelType]}/download/${taskId}`;
          const a = document.createElement('a');
          a.href = downloadUrl;
          a.download = data.filename || 'resultado.xlsx';
          document.body.appendChild(a);
          a.click();
          a.remove();

          setStatusMessage(`Processo finalizado! Download iniciado: ${data.filename}`);
          setIsProcessing(false);
          setShowProgressModal(false);
          setCurrentTaskId(null);

          // Limpar intervalo
          if (progressIntervalRef.current) {
            clearInterval(progressIntervalRef.current);
            progressIntervalRef.current = null;
          }
        } else if (data.status === 'error') {
          setStatusMessage(`Erro: ${data.error || 'Erro desconhecido'}`);
          setIsProcessing(false);
          setShowProgressModal(false);
          setCurrentTaskId(null);

          // Limpar intervalo
          if (progressIntervalRef.current) {
            clearInterval(progressIntervalRef.current);
            progressIntervalRef.current = null;
          }
        }
      }
    } catch (error) {
      console.error('Erro ao verificar progresso:', error);
    }
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
    setShowProgressModal(true);
    setProgressData({
      current_step: 0,
      total_steps: 10,
      progress: 0,
      message: 'Iniciando processamento...'
    });
    setStatusMessage('Iniciando processamento...');

    const apiUrl = `${API_URLS[modelType]}/process`;

    const formData = new FormData();
    formData.append('pdf_file', selectedFile);
    formData.append('pages', pageRange);
    formData.append('model_type', modelType);

    try {
      const response = await fetch(apiUrl, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorResult = await response.json();
        throw new Error(errorResult.error || 'Ocorreu um erro no servidor.');
      }

      const result = await response.json();
      const taskId = result.task_id;
      setCurrentTaskId(taskId);

      // Iniciar monitoramento do progresso
      progressIntervalRef.current = setInterval(() => {
        checkProgress(taskId);
      }, 1000); // Verificar a cada 1 segundo

    } catch (error) {
      console.error('Ocorreu um erro:', error);
      setStatusMessage(`Erro: ${error.message}`);
      setIsProcessing(false);
      setShowProgressModal(false);
    }
  };

  const handleCloseModal = () => {
    // Permitir fechar o modal, mas continuar o processamento em background
    setShowProgressModal(false);
  };

  // Limpar intervalo quando o componente for desmontado
  useEffect(() => {
    return () => {
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current);
      }
    };
  }, []);

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
              Ponto Santander (Modelo 2)
            </label>
            <label>
              <input
                type="radio"
                name="modelType"
                value="teste"
                checked={modelType === 'teste'}
                onChange={(e) => {
                  setModelType(e.target.value);
                  setSelectedModelImage(null);
                }}
              />
              Teste (Debug)
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

      {/* Modal de Progresso */}
      {showProgressModal && (
        <ProgressModal
          current={progressData.current_step}
          total={progressData.total_steps}
          onClose={handleCloseModal}
        />
      )}
    </div>
  );
}

export default App;