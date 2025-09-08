// src/hooks/useRemoveNBSP.js
import { useEffect } from 'react';

const useRemoveNBSP = () => {
  useEffect(() => {
    const removeNonBreakingSpaces = () => {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        if (node.nodeValue.includes('\u00A0')) { // Otimização: só substitui se encontrar o caractere
          node.nodeValue = node.nodeValue.replace(/\u00A0/g, ' ');
        }
      }
    };

    // Executa a função na montagem inicial
    removeNonBreakingSpaces();

    // Opcional: Você pode querer re-executar se o DOM mudar dinamicamente após a montagem inicial.
    // Para a maioria dos casos de uso, a execução inicial é suficiente.
    // Se o conteúdo for carregado assincronamente ou renderizado após a montagem,
    // você pode precisar de um MutationObserver, mas para um efeito global simples,
    // o useEffect inicial é geralmente o que se busca.

  }, []); // O array vazio garante que o efeito só rode uma vez na montagem
};

export default useRemoveNBSP;
