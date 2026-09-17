// frontend/src/novo/ModalPeriodos.tsx
//
// Confirmacao dos periodos do cartao de ponto.
//
// A logica e' copia fiel do PontoExtractorPage atual: mesma deteccao de
// multiplas regioes, mesma deteccao de sobreposicao, mesmo "aplicar padrao
// mensal", mesma chamada a /api/process com o mesmo corpo. So' a forma mudou.
// Foi copiado em vez de importado para que o arquivo antigo continue
// exatamente como esta' — enquanto os clientes usarem ele, ele nao se mexe.

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Calendar, ChevronRight, Loader2, Play, ToggleLeft, ToggleRight, X } from "lucide-react";
import { toast } from "sonner";

export interface Periodo {
  start_date: string;
  end_date: string;
  confidence?: string;
}

export interface InfoPagina {
  page_number: number;
  page_index: number;
  period: Periodo | null;
  is_active: boolean;
  bbox?: number[] | null;
  label?: string;
  region_id?: number;
}

const DATA_RE = /^\d{2}\/\d{2}\/\d{4}$/;

function mascaraData(valor: string): string {
  const v = valor.replace(/\D/g, "").slice(0, 8);
  if (v.length > 4) return `${v.slice(0, 2)}/${v.slice(2, 4)}/${v.slice(4)}`;
  if (v.length > 2) return `${v.slice(0, 2)}/${v.slice(2)}`;
  return v;
}

export default function ModalPeriodos({
  paginas,
  caminhoPdf,
  turnoNoturno,
  aoFechar,
  aoConfirmar,
  aoFaltarSaldo,
  buscar,
}: {
  paginas: InfoPagina[];
  caminhoPdf: string;
  turnoNoturno: boolean;
  aoFechar: () => void;
  aoConfirmar: (taskId: string) => void;
  aoFaltarSaldo: (pedidas: number, disponiveis: number) => void;
  buscar: (url: string, options?: RequestInit) => Promise<Response>;
}) {
  const [itens, setItens] = useState<InfoPagina[]>(
    paginas.map((p) => ({
      ...p,
      is_active: true,
      period: p.period ?? { start_date: "", end_date: "" },
    }))
  );
  const [carregando, setCarregando] = useState(false);
  const [mostrarPares, setMostrarPares] = useState(false);

  const ativas = itens.filter((p) => p.is_active).length;

  const temMultiplasRegioes = useMemo(() => {
    const contas = new Map<number, number>();
    for (const item of itens) contas.set(item.page_index, (contas.get(item.page_index) ?? 0) + 1);
    return Array.from(contas.values()).some((c) => c > 1);
  }, [itens]);

  const paresSobrepostos = useMemo(() => {
    const paraData = (s: string): Date | null => {
      if (!DATA_RE.test(s)) return null;
      const [d, m, y] = s.split("/");
      return new Date(+y, +m - 1, +d);
    };
    const ativos = itens
      .map((item, idx) => ({ item, idx }))
      .filter(
        ({ item }) =>
          item.is_active &&
          item.period &&
          DATA_RE.test(item.period.start_date) &&
          DATA_RE.test(item.period.end_date)
      );
    const pares: Array<{ aPag: number; bPag: number }> = [];
    for (let i = 0; i < ativos.length; i++) {
      for (let j = i + 1; j < ativos.length; j++) {
        const a = ativos[i];
        const b = ativos[j];
        if (a.item.page_index === b.item.page_index) continue;
        const aS = paraData(a.item.period!.start_date)!;
        const aE = paraData(a.item.period!.end_date)!;
        const bS = paraData(b.item.period!.start_date)!;
        const bE = paraData(b.item.period!.end_date)!;
        if (aS <= bE && bS <= aE) {
          pares.push({ aPag: a.item.page_number, bPag: b.item.page_number });
        }
      }
    }
    return pares;
  }, [itens]);

  const mudarData = (indice: number, campo: keyof Periodo, bruto: string) => {
    const val = mascaraData(bruto);
    setItens((prev) => {
      const prox = [...prev];
      prox[indice] = {
        ...prox[indice],
        period: { ...(prox[indice].period ?? { start_date: "", end_date: "" }), [campo]: val },
      };
      return prox;
    });
  };

  const alternar = (indice: number) => {
    setItens((prev) => {
      const prox = [...prev];
      prox[indice] = { ...prox[indice], is_active: !prox[indice].is_active };
      return prox;
    });
  };

  const aplicarPadrao = (inicio: number) => {
    const semente = itens[inicio]?.period;
    if (!semente || !DATA_RE.test(semente.start_date) || !DATA_RE.test(semente.end_date)) {
      toast.warning("Preencha o período completo (DD/MM/AAAA) antes de aplicar.");
      return;
    }
    const ler = (s: string) => {
      const [d, m, y] = s.split("/");
      return new Date(+y, +m - 1, +d);
    };
    const escrever = (dt: Date) =>
      `${String(dt.getDate()).padStart(2, "0")}/${String(dt.getMonth() + 1).padStart(2, "0")}/${dt.getFullYear()}`;
    const ehUltimoDia = (dt: Date) => {
      const prox = new Date(dt);
      prox.setDate(prox.getDate() + 1);
      return prox.getDate() === 1;
    };
    let ultimoInicio = ler(semente.start_date);
    let ultimoFim = ler(semente.end_date);
    const fimEraUltimo = ehUltimoDia(ultimoFim);
    setItens((prev) => {
      const prox = [...prev];
      for (let i = inicio + 1; i < prox.length; i++) {
        if (!prox[i].is_active) continue;
        if (prox[i].page_index === prox[inicio].page_index) continue;
        const ns = new Date(ultimoInicio);
        ns.setMonth(ns.getMonth() + 1);
        const ne = fimEraUltimo
          ? new Date(ns.getFullYear(), ns.getMonth() + 1, 0)
          : (() => { const d = new Date(ultimoFim); d.setMonth(d.getMonth() + 1); return d; })();
        prox[i] = { ...prox[i], period: { start_date: escrever(ns), end_date: escrever(ne) } };
        ultimoInicio = ns;
        ultimoFim = ne;
      }
      return prox;
    });
  };

  const confirmar = async () => {
    const validas = itens.filter(
      (p) => p.is_active && p.period && DATA_RE.test(p.period.start_date) && DATA_RE.test(p.period.end_date)
    );
    if (validas.length === 0) {
      toast.warning("Preencha o período (DD/MM/AAAA) de pelo menos uma página ativa.");
      return;
    }
    setCarregando(true);
    try {
      const res = await buscar("/api/process", {
        method: "POST",
        body: JSON.stringify({
          pdf_path: caminhoPdf,
          pages_with_periods: validas,
          model_type: "6",
          turno_noturno: turnoNoturno,
        }),
      });
      const dados = await res.json();

      if (res.status === 403) {
        aoFaltarSaldo(dados.pages_requested ?? validas.length, dados.balance ?? 0);
        return;
      }
      if (res.ok && dados.task_id) {
        toast.success("Processamento iniciado!");
        aoConfirmar(dados.task_id);
      } else {
        toast.error(dados.error || "Erro ao iniciar processamento.");
      }
    } catch {
      toast.error("Erro de conexão.");
    } finally {
      setCarregando(false);
    }
  };

  const classeData = (valor: string | undefined) =>
    valor && DATA_RE.test(valor)
      ? "border-success/50 focus:border-success/80 focus:ring-1 focus:ring-success/20"
      : "border-border/50 focus:border-primary/60 focus:ring-1 focus:ring-primary/20";

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 p-4 backdrop-blur-sm"
      >
        <motion.div
          initial={{ scale: 0.95, y: 10 }}
          animate={{ scale: 1, y: 0 }}
          exit={{ scale: 0.95, y: 10 }}
          className="glass-card relative flex max-h-[85vh] w-full max-w-3xl flex-col"
        >
          <div className="flex shrink-0 items-center justify-between border-b border-border/50 p-6">
            <div className="flex items-center gap-3">
              <Calendar className="h-5 w-5 text-primary" />
              <h3 className="text-lg font-bold text-foreground">Confirmar períodos</h3>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground">{ativas} região(ões) ativa(s)</span>
              <button onClick={aoFechar} className="text-muted-foreground transition-colors hover:text-foreground">
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>

          {temMultiplasRegioes && (
            <div className="shrink-0 border-b border-border/30 bg-primary/5 px-6 py-2">
              <p className="text-xs text-muted-foreground">
                Algumas páginas têm mais de uma tabela. Cada uma aparece como uma linha separada.
              </p>
            </div>
          )}

          <div className="flex-1 space-y-2 overflow-y-auto p-4">
            {itens.map((pagina, indice) => {
              const multi = indice > 0 && itens[indice - 1].page_index === pagina.page_index;
              return (
                <div
                  key={`${pagina.page_index}-${pagina.region_id ?? 0}`}
                  className={`flex items-center gap-3 rounded-xl border p-3 transition-all ${
                    pagina.is_active
                      ? "border-border/50 bg-secondary/20"
                      : "border-border/20 bg-secondary/5 opacity-45"
                  } ${multi ? "ml-6 border-dashed" : ""}`}
                >
                  <button
                    onClick={() => alternar(indice)}
                    className="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {pagina.is_active
                      ? <ToggleRight className="h-5 w-5 text-primary" />
                      : <ToggleLeft className="h-5 w-5" />}
                  </button>

                  <div className="min-w-[56px] shrink-0">
                    <p className="text-xs font-semibold leading-tight text-foreground">
                      Pág {pagina.page_number}
                    </p>
                    {pagina.label && (
                      <p className="text-[10px] leading-tight text-muted-foreground">{pagina.label}</p>
                    )}
                  </div>

                  <div className="flex min-w-0 flex-1 items-center gap-2">
                    <input
                      type="text"
                      value={pagina.period?.start_date ?? ""}
                      onChange={(e) => mudarData(indice, "start_date", e.target.value)}
                      placeholder="DD/MM/AAAA"
                      maxLength={10}
                      disabled={!pagina.is_active}
                      className={`w-full rounded-lg border bg-background/60 px-3 py-2 text-sm text-foreground transition-all focus:outline-none disabled:opacity-40 ${classeData(pagina.period?.start_date)}`}
                    />
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <input
                      type="text"
                      value={pagina.period?.end_date ?? ""}
                      onChange={(e) => mudarData(indice, "end_date", e.target.value)}
                      placeholder="DD/MM/AAAA"
                      maxLength={10}
                      disabled={!pagina.is_active}
                      className={`w-full rounded-lg border bg-background/60 px-3 py-2 text-sm text-foreground transition-all focus:outline-none disabled:opacity-40 ${classeData(pagina.period?.end_date)}`}
                    />
                    <button
                      onClick={() => aplicarPadrao(indice)}
                      disabled={!pagina.is_active}
                      title="Preencher as próximas páginas com padrão mensal"
                      className="whitespace-nowrap rounded-lg bg-primary/10 px-2 py-1.5 text-xs font-medium text-primary transition-all hover:bg-primary/20 disabled:opacity-30"
                    >
                      Aplicar ↓
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="shrink-0 border-t border-border/50 p-6">
            {paresSobrepostos.length > 0 && (
              <div className="mb-3 overflow-hidden rounded-lg border border-warning/50 bg-warning/10">
                <div
                  className="flex cursor-pointer select-none items-center gap-2 px-4 py-2.5"
                  onClick={() => setMostrarPares((v) => !v)}
                >
                  <span className="text-base">⚠</span>
                  <span className="text-sm font-semibold text-warning">
                    Sobreposição de períodos detectada
                  </span>
                  <span className="whitespace-nowrap rounded-full bg-warning px-2 py-0.5 text-xs font-medium text-warning-foreground">
                    {paresSobrepostos.length} {paresSobrepostos.length === 1 ? "par" : "pares"}
                  </span>
                  <span className="flex-1" />
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); setMostrarPares((v) => !v); }}
                    className="flex items-center gap-1 whitespace-nowrap rounded-lg border border-warning/40 px-2.5 py-1 text-xs text-warning transition-all hover:bg-warning/10"
                    aria-expanded={mostrarPares}
                  >
                    {mostrarPares ? "Ocultar" : "Ver pares"}
                    <ChevronRight className={`h-3.5 w-3.5 transition-transform ${mostrarPares ? "rotate-90" : ""}`} />
                  </button>
                </div>
                <p className="px-4 pb-2.5 text-xs leading-snug text-warning/90">
                  Esses pares cobrem datas em comum e misturam dados no mesmo dia. Corrija antes de processar.
                </p>
                {mostrarPares && (
                  <div className="max-h-32 overflow-y-auto border-t border-warning/25">
                    <div className="grid grid-cols-3 gap-x-4 gap-y-0.5 px-4 py-2.5">
                      {paresSobrepostos.map(({ aPag, bPag }, i) => (
                        <span key={i} className="whitespace-nowrap text-xs text-warning/90">
                          Pág {aPag} ↔ {bPag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={aoFechar}
                disabled={carregando}
                className="flex-1 rounded-lg border border-border py-3 text-sm font-medium text-foreground transition-all hover:bg-surface-hover disabled:opacity-50"
              >
                Cancelar
              </button>
              <button
                onClick={confirmar}
                disabled={carregando || ativas === 0}
                className="flex flex-1 items-center justify-center gap-2 rounded-xl gradient-primary py-3 text-sm font-bold text-primary-foreground transition-all hover:shadow-lg hover:shadow-primary/25 disabled:opacity-50"
              >
                {carregando
                  ? <><Loader2 className="h-4 w-4 animate-spin" /> Iniciando...</>
                  : <><Play className="h-4 w-4" /> Confirmar e extrair</>}
              </button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
