// src/MainApp.js
import React, { useState, useRef, useEffect } from 'react';
import './App.css';
import ProgressModal from './ProgressModal';

const API_BASE_URL = '/api'; // Usa o proxy configurado no package.json

// Mapeamento de caminhos das imagens dos modelos
const MODEL_IMAGE_PATHS = {
  '1': process.env.PUBLIC_URL + '/Modelo1.png',
  '2': process.env.PUBLIC_URL + '/Modelo2.png',
  '3': process.env.PUBLIC_URL + '/Modelo3.png',
  '4': process.env.PUBLIC_URL + '/Modelo4.png'
};

function MainApp({ onLogout }) { // Recebe onLogout como prop
  const [selectedFile, setSelectedFile] = useState(null);
  const [pageRange, setPageRange] = useState('');
  const [modelType, setModelType] = useState('1');
  const [statusMessage, setStatusMessage] = useState('Aguardando arquivo...');
  const [isProcessing, setIsProcessing] = useState(false);
  const [showModelOptions, setShowModelOptions] = useState(false);
  const [selectedModelImage, setSelectedModelImage] = useState(MODEL_IMAGE_PATHS['1']);
  const [showProgressModal, setShowProgressModal] = useState(false);
  const [currentTaskId, setCurrentTaskId] = useState(null);
  const [progressData, setProgressData] = useState({
    current_step: 0,
    total_steps: 1,
    progress: 0,
    message: 'Iniciando...'
  });
  const fileInputRef = useRef(null);
  const progressIntervalRef = useRef(null);

  useEffect(() => {
    // Pré-carrega as imagens dos modelos
    Object.values(MODEL_IMAGE_PATHS).forEach(path => {
      if (path) {
        const img = new Image();
        img.src = path;
      }
    });
  }, []);

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
    const token = localStorage.getItem('jwt_token'); // Obtém o token JWT
    if (!token) {
        // Se não houver token, força o logout
        onLogout();
        return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/progress/${taskId}`, {
        headers: {
          'Authorization': `Bearer ${token}` // Adiciona o token JWT
        }
      });

      if (response.status === 401 || response.status === 403) {
        // Token inválido ou expirado, ou acesso negado
        const errorData = await response.json();
        alert(errorData.error || errorData.msg || 'Sua sessão expirou ou você não tem permissão.');
        onLogout(); // Força o logout
        return;
      }

      if (response.ok) {
        const data = await response.json();
        setProgressData({
          current_step: data.current_step || 0,
          total_steps: data.total_steps || 1,
          progress: data.progress || 0,
          message: data.message || 'Processando...'
        });
        setStatusMessage(data.message || 'Processando...');

        if (data.status === 'completed') {
          // Para download com JWT, é melhor fazer um fetch e criar um Blob
          const downloadResponse = await fetch(`${API_BASE_URL}/download/${taskId}`, {
            headers: {
              'Authorization': `Bearer ${token}` // Adiciona o token JWT
            }
          });

          if (downloadResponse.ok) {
            const blob = await downloadResponse.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = data.filename || 'resultado.csv';
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url); // Libera o objeto URL
            setStatusMessage(`Processo finalizado! Download iniciado: ${data.filename}`);
          } else {
            const errorDownloadData = await downloadResponse.json();
            setStatusMessage(`Erro ao baixar o arquivo: ${errorDownloadData.error || 'Erro desconhecido'}`);
          }

          setIsProcessing(false);
          setShowProgressModal(false);
          setCurrentTaskId(null);
          if (progressIntervalRef.current) {
            clearInterval(progressIntervalRef.current);
            progressIntervalRef.current = null;
          }
        } else if (data.status === 'error') {
          setStatusMessage(`Erro: ${data.error || data.message || 'Erro desconhecido'}`);
          setIsProcessing(false);
          setShowProgressModal(false);
          setCurrentTaskId(null);
          if (progressIntervalRef.current) {
            clearInterval(progressIntervalRef.current);
            progressIntervalRef.current = null;
          }
        }
      } else {
        const errorData = await response.json();
        console.error('Erro ao verificar progresso:', errorData.error || errorData.msg);
        if (response.status === 401 || response.status === 403) {
            alert(errorData.error || errorData.msg || 'Sua sessão expirou ou você não tem permissão.');
            onLogout(); // Força o logout
            return;
        }
        setProgressData(prev => ({
          ...prev,
          message: `Erro ao verificar progresso: ${errorData.error || errorData.msg}`,
          status: 'error'
        }));
        setStatusMessage(`Erro ao verificar progresso: ${errorData.error || errorData.msg}`);
        setIsProcessing(false);
        setShowProgressModal(false);
        setCurrentTaskId(null);
        if (progressIntervalRef.current) {
          clearInterval(progressIntervalRef.current);
          progressIntervalRef.current = null;
        }
      }
    } catch (error) {
      console.error('Erro de rede ao verificar progresso:', error);
      setProgressData(prev => ({
        ...prev,
        message: `Erro de rede ao verificar progresso: ${error.message}`,
        status: 'error'
      }));
      setStatusMessage(`Erro de rede: ${error.message}`);
      setIsProcessing(false);
      setShowProgressModal(false);
      setCurrentTaskId(null);
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current);
        progressIntervalRef.current = null;
      }
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
      total_steps: 1,
      progress: 0,
      message: 'Iniciando processamento...'
    });
    setStatusMessage('Iniciando processamento...');

    const apiUrl = `${API_BASE_URL}/process`;
    const formData = new FormData();
    formData.append('pdf_file', selectedFile);
    formData.append('pages', pageRange);
    formData.append('model_type', modelType);

    const token = localStorage.getItem('jwt_token'); // Obtém o token JWT
    if (!token) {
        onLogout(); // Se não houver token, força o logout
        return;
    }

    try {
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}` // Adiciona o token JWT aqui!
        },
        body: formData,
      });

      if (response.status === 401 || response.status === 403) {
        // Token inválido ou expirado, ou acesso negado (ex: conta inativa)
        const errorResult = await response.json();
        alert(errorResult.error || errorResult.msg || 'Sua sessão expirou ou você não tem permissão.');
        onLogout(); // Força o logout
        return;
      }

      if (!response.ok) {
        const errorResult = await response.json();
        throw new Error(errorResult.error || errorResult.msg || 'Ocorreu um erro no servidor.');
      }

      const result = await response.json();
      const taskId = result.task_id;
      setCurrentTaskId(taskId);
      // Inicia o polling de progresso
      progressIntervalRef.current = setInterval(() => {
        checkProgress(taskId);
      }, 1000); // Poll a cada 1 segundo
    } catch (error) {
      console.error('Ocorreu um erro:', error);
      setStatusMessage(`Erro: ${error.message}`);
      setIsProcessing(false);
      setShowProgressModal(false);
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current);
        progressIntervalRef.current = null;
      }
    }
  };

  const handleCloseModal = () => {
    setShowProgressModal(false);
  };

  useEffect(() => {
    return () => {
      if (progressIntervalRef.current) {
        clearInterval(progressIntervalRef.current);
      }
    };
  }, []);

  return (
    <div className="App">
      <header className="title">
        <h1>Extrator de Pontos</h1>
        <button onClick={onLogout} className="logout-button">Sair</button> {/* Botão de sair */}
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
                  setSelectedModelImage(MODEL_IMAGE_PATHS['1']);
                }}
              />
              JBS Ponto (Modelo 1)
            </label>
            <label>
              <input
                type="radio"
                name="modelType"
                value="2"
                checked={modelType === '2'}
                onChange={(e) => {
                  setModelType(e.target.value);
                  setSelectedModelImage(MODEL_IMAGE_PATHS['2']);
                }}
              />
              BRF Ponto (Modelo 2)
            </label>
            <label>
              <input
                type="radio"
                name="modelType"
                value="3"
                checked={modelType === '3'}
                onChange={(e) => {
                  setModelType(e.target.value);
                  setSelectedModelImage(MODEL_IMAGE_PATHS['3']);
                }}
              />
              Ponto Mais (Modelo 3)
            </label>
            <label>
              <input
                type="radio"
                name="modelType"
                value="4"
                checked={modelType === '4'}
                onChange={(e) => {
                  setModelType(e.target.value);
                  setSelectedModelImage(MODEL_IMAGE_PATHS['4']);
                }}
              />
              Minuano (Modelo 4)
            </label>
            {MODEL_IMAGE_PATHS[modelType] && (
              <div style={{ marginTop: '15px' }}>
                <img
                  src={MODEL_IMAGE_PATHS[modelType]}
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
      {showProgressModal && (
        <ProgressModal
          current={progressData.current_step}
          total={progressData.total_steps}
          onClose={handleCloseModal}
          message={progressData.message}
        />
      )}
    </div>
  );
}
export default MainApp;

