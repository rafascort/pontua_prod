// src/apiUtils.js

// Função para ser chamada quando um 401 for detectado
let onUnauthorizedCallback = () => {
  console.error("Callback de não autorizado não configurado. Redirecionando para /login.");
  // Comportamento padrão: limpar token e redirecionar
  localStorage.removeItem('jwt_token');
  // Usar window.location.href força um recarregamento completo para a página de login
  window.location.href = '/login?sessionExpired=true'; // Adiciona um parâmetro para mostrar mensagem
};

// Função para configurar o callback de logout a partir do App.js
export const setUnauthorizedCallback = (callback) => {
  if (typeof callback === 'function') {
    onUnauthorizedCallback = callback;
  } else {
    console.error("Tentativa de configurar callback inválido para não autorizado.");
  }
};

// Wrapper para a função fetch que adiciona o token e trata o 401
export const fetchWithAuth = async (url, options = {}) => {
  const token = localStorage.getItem('jwt_token');

  // Adiciona o cabeçalho de autorização se o token existir
  if (token) {
    options.headers = {
      ...options.headers,
      'Authorization': `Bearer ${token}`,
    };
  } else {
    // Se não há token, chama imediatamente o callback de não autorizado
    console.warn("fetchWithAuth: Nenhum token encontrado. Chamando callback de não autorizado.");
    onUnauthorizedCallback();
    // Lança um erro para interromper a chamada fetch
    throw new Error('Não autenticado.');
  }

  // Define Content-Type para JSON se houver body e não for FormData
  if (options.body && !(options.body instanceof FormData) && (!options.headers || !options.headers['Content-Type'])) {
      options.headers = {
          ...options.headers,
          'Content-Type': 'application/json',
      };
  }

  try {
    const response = await fetch(url, options);

    // Verifica especificamente se a resposta é 401 Unauthorized
    if (response.status === 401) {
      console.warn(`Recebido status 401 (Não Autorizado) para ${url}. Chamando callback.`);
      onUnauthorizedCallback(); // Chama a função de logout/redirecionamento configurada
      // Lança um erro para interromper o fluxo normal
      throw new Error('Sessão expirada ou inválida.');
    }

    // Se não for 401, retorna a resposta para ser tratada normalmente
    return response;

  } catch (error) {
    // Se o erro for o 401 que lançamos, ou um erro de rede, repassa
    // Evita logar o erro "Sessão expirada..." como um erro inesperado
    if (error.message !== 'Sessão expirada ou inválida.' && error.message !== 'Não autenticado.') {
        console.error("Erro na chamada fetch:", error);
    }
    throw error; // Repassa o erro para quem chamou a função poder tratar (ex: mostrar mensagem)
  }
};
