// frontend/src/novo/bookmarklet.ts
//
// O codigo do favorito do PJe, em texto, mais o construtor que troca o token e
// o destino.
//
// Por que o codigo inteiro vive aqui e aparece na tela: um favorito que BUSCA
// codigo de fora pode mudar sozinho depois de instalado — o perito autorizaria
// uma coisa e passaria a rodar outra. Este nao busca nada. O que ele faz e' o
// que esta' escrito, e depois de instalado fica congelado: mudar exige o perito
// instalar de novo. "Confie que nao vamos mudar" vira "nao temos como mudar".
//
// Fonte unica: a tela mostra ESTA string. Nao existe versao "de exibicao"
// diferente da que e' instalada.

export const FONTE = `(async () => {
  const TOKEN = '__TOKEN__';
  const DESTINO = '__DESTINO__';
  const API = '/pje-comum-api/api/pericias';

  const caixa = document.createElement('div');
  caixa.style.cssText = 'position:fixed;z-index:2147483647;right:16px;bottom:16px;width:330px;font:13px/1.5 system-ui,-apple-system,sans-serif;background:#131a2e;color:#e6ecf7;border:1px solid #2b3557;border-radius:12px;padding:14px 16px;box-shadow:0 12px 32px rgba(0,0,0,.45)';
  const topo = document.createElement('div');
  topo.style.cssText = 'font-weight:700;margin-bottom:2px';
  topo.textContent = 'Sistema Ponto - lendo o PJe';
  const fechar = document.createElement('span');
  fechar.textContent = 'x';
  fechar.style.cssText = 'float:right;cursor:pointer;opacity:.6;padding:0 4px';
  fechar.onclick = () => caixa.remove();
  topo.appendChild(fechar);
  caixa.appendChild(topo);
  document.body.appendChild(caixa);
  const diz = (t, cor) => {
    const l = document.createElement('div');
    l.style.cssText = 'margin-top:6px;color:' + (cor || '#9fb0d0');
    l.textContent = t;
    caixa.appendChild(l);
    return l;
  };

  if (!/\\.jus\\.br$/.test(location.hostname)) {
    diz('Abra o PJe no perfil Perito e clique aqui de novo.', '#f0b429');
    return;
  }

  async function todas(qs) {
    let pag = 1, out = [];
    while (true) {
      const r = await fetch(API + '?' + qs + '&pagina=' + pag + '&tamanhoPagina=200', { credentials: 'include' });
      if (r.status === 401 || r.status === 403) throw new Error('SESSAO');
      if (!r.ok) throw new Error('O PJe respondeu ' + r.status + '.');
      const j = await r.json();
      out = out.concat(j.resultado || []);
      if (!j.qtdPaginas || pag >= j.qtdPaginas) break;
      pag++;
      if (pag > 60) break;
    }
    return out;
  }

  const mapa = p => {
    const perm = p.permissoesPericia || {};
    return {
      processo: p.numeroProcesso,
      situacao: (p.situacao || {}).codigo,
      situacaoTexto: (p.situacao || {}).descricao,
      situacaoPericia: p.situacaoPericia,
      prazoEntrega: (p.prazoEntrega || '').slice(0, 10),
      dataAceite: (p.dataAceite || '').slice(0, 10),
      dataCriacao: (p.dataCriacao || '').slice(0, 10),
      tarefa: p.tarefa || '',
      partes: p.partes || '',
      orgao: p.nomeOrgaoJulgador || '',
      fase: p.fase || '',
      prioridade: !!p.prioridadeProcessual,
      expedienteAberto: !!p.possuiExpedienteAberto,
      cienciaPendente: !!perm.permitidoTomarCienciaIntimacao,
      podeJuntarLaudo: !!perm.permitidoJuntarLaudo,
      podeJuntarEsclarecimentos: !!perm.permitidoJuntarEsclarecimentos,
      podeAceitarOuRecusar: !!perm.permitidoAceitarOuRecusar,
      laudoJuntado: !!p.laudoJuntado,
      arquivado: !!p.arquivado,
      classe: p.siglaClasseJudicialProcesso || '',
      idPericia: p.id,
      idProcesso: p.idProcesso
    };
  };

  const linha = diz('lendo as suas pericias...');
  let vivas, finais, arquiv, intim;
  try {
    vivas = await todas('situacao=M&situacao=L&situacao=A&situacao=S&situacao=P&situacao=D');
    linha.textContent = 'em andamento: ' + vivas.length;
    finais = await todas('situacao=F&situacao=N');
    arquiv = await todas('arquivadas=true');
    intim = await todas('intimacoes=true');
  } catch (e) {
    if (String(e.message) === 'SESSAO') {
      diz('A sua sessao do PJe expirou. Recarregue a pagina, entre de novo e clique aqui.', '#f0b429');
    } else {
      diz(String(e.message || e), '#f97066');
    }
    return;
  }

  const perfil = vivas[0] || finais[0] || arquiv[0] || {};
  const dados = {
    gerado_em: new Date().toISOString(),
    perito: perfil.nomePerito || '',
    idPerito: perfil.idPerito || null,
    tribunal: location.hostname.replace(/^pje\\./, '').split('.')[0].toUpperCase(),
    origem: location.hostname,
    vivas: vivas.map(mapa),
    finalizadas: finais.map(mapa),
    arquivadas: arquiv.map(mapa),
    intimacoes: intim.map(mapa),
    intimacoes_bruto: intim
  };

  diz('finalizadas: ' + finais.length + '  arquivadas: ' + arquiv.length + '  intimacoes: ' + intim.length);

  const baixar = () => {
    const b = new Blob([JSON.stringify({ token: '', dados: dados })], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(b);
    a.download = 'pje_' + dados.tribunal + '_' + dados.gerado_em.slice(0, 10) + '.json';
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const corpo = JSON.stringify({ token: TOKEN, dados: dados });
  const mb = (corpo.length / 1048576).toFixed(1);

  // Subir alguns MB pela banda de casa leva dezenas de segundos. Sem contador
  // a caixinha fica muda e parece travada - foi o que aconteceu no primeiro
  // teste real, e o perito desistiu antes de a resposta chegar.
  const barra = diz('enviando ' + mb + ' MB... 0s');
  const inicio = Date.now();
  const relogio = setInterval(() => {
    const s = Math.round((Date.now() - inicio) / 1000);
    barra.textContent = 'enviando ' + mb + ' MB... ' + s + 's'
      + (s > 20 ? '  (normal ate 1 min)' : '');
  }, 1000);

  const corte = new AbortController();
  const alarme = setTimeout(() => corte.abort(), 180000);

  try {
    const r = await fetch(DESTINO, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain;charset=UTF-8' },
      body: corpo,
      signal: corte.signal
    });
    clearInterval(relogio); clearTimeout(alarme);
    const seg = Math.round((Date.now() - inicio) / 1000);
    barra.textContent = 'enviado em ' + seg + 's';
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      diz('O Sistema Ponto recusou: ' + (j.msg || r.status), '#f97066');
      if (r.status === 401) diz('Gere um favorito novo no painel e substitua este.', '#f0b429');
      return;
    }
    diz('Pronto. ' + (j.vivas || 0) + ' pericias em andamento no painel.', '#5fd08a');
    diz('Pode fechar. Confira em Pericias > Ligar o PJe.');
  } catch (e) {
    clearInterval(relogio); clearTimeout(alarme);
    const abortou = e && e.name === 'AbortError';
    diz(abortou
      ? 'Passou de 3 minutos e eu cortei. Baixei o arquivo:'
      : 'Nao consegui enviar daqui. Baixei o arquivo:', '#f0b429');
    diz('suba ele em Pericias > Ligar o PJe > Escolher arquivo.', '#f0b429');
    baixar();
  }
})();`;

/** Troca token e destino e devolve o texto pronto para virar favorito. */
export function montarFonte(token: string, destino: string) {
  return FONTE.replace("__TOKEN__", token).replace("__DESTINO__", destino);
}

/** O valor do href do favorito. */
export function montarHref(token: string, destino: string) {
  return "javascript:" + encodeURIComponent(montarFonte(token, destino));
}
