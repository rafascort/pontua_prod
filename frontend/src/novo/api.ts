// frontend/src/novo/api.ts
//
// Mesmo acesso a' API das telas atuais: token do localStorage, Bearer no
// header, Content-Type so' quando o corpo nao e' FormData. Copiado igual de
// proposito — o layout mudou, a conversa com o backend nao.

export function pegarToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("jwt_token");
}

export async function buscar(url: string, options: RequestInit = {}) {
  const token = pegarToken();
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    ...(options.headers as Record<string, string>),
  };
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  return fetch(url, { ...options, headers });
}

/** "1-10, 15, 20-25" -> 17 */
export function contarPaginas(intervalo: string): number {
  if (!intervalo.trim()) return 0;
  let total = 0;
  for (const parte of intervalo.split(",").map((s) => s.trim())) {
    if (parte.includes("-")) {
      const [i, f] = parte.split("-").map(Number);
      if (!isNaN(i) && !isNaN(f) && f >= i) total += f - i + 1;
    } else if (!isNaN(Number(parte)) && parte) {
      total += 1;
    }
  }
  return total;
}

export function baixar(blob: Blob, nome: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
