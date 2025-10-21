// src/authUtils.js

/**
 * Decodifica um token JWT.
 * @param {string} token O token JWT.
 * @returns {object|null} O payload decodificado ou null se houver erro.
 */
export const decodeToken = (token) => {
    if (!token) return null;
    try {
        const base64Url = token.split('.')[1];
        if (!base64Url) return null; // Verifica se a parte do payload existe
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        // Adiciona padding se necessário e decodifica
        const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
        }).join(''));
        const decodedToken = JSON.parse(jsonPayload);
        return decodedToken;
    } catch (e) {
        console.error("Erro ao decodificar token JWT:", e);
        return null;
    }
};

/**
 * Verifica se o token JWT no localStorage é válido (existe, não expirado e conta ativa).
 * @returns {boolean} True se o token for válido, False caso contrário.
 */
export const isTokenValid = () => {
    const token = localStorage.getItem('jwt_token');
    if (!token) {
        // console.log("Verificação de token: Nenhum token encontrado.");
        return false; // Não há token
    }

    const decodedToken = decodeToken(token);
    if (!decodedToken) {
        console.warn("Verificação de token: Token inválido encontrado, limpando.");
        localStorage.removeItem('jwt_token'); // Limpa token inválido
        return false; // Token inválido
    }

    const currentTime = Date.now() / 1000; // Tempo atual em segundos

    // Verifica expiração
    if (decodedToken.exp < currentTime) {
         console.log(`Verificação de token: Expirado (exp: ${decodedToken.exp}, now: ${currentTime})`);
         localStorage.removeItem('jwt_token'); // Limpa token expirado
         return false;
    }

    // Verifica se a conta está ativa (se a claim 'is_active' existir)
    if (typeof decodedToken.is_active !== 'undefined' && !decodedToken.is_active) {
        console.log("Verificação de token: Conta inativa.");
        localStorage.removeItem('jwt_token'); // Limpa token de conta inativa
        return false;
    }

    // console.log("Verificação de token: Válido.");
    return true; // Token válido e ativo
};
