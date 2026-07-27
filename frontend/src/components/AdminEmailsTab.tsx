// frontend/src/components/AdminEmailsTab.tsx
//
// Aba de acompanhamento dos e-mails do ciclo de vida.
// Componente de secao (sem moldura de pagina) — mesmo padrao das
// outras abas do painel admin.
import { useState, useEffect, useCallback } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

interface UltimoEmail {
  tipo: string;
  rotulo: string;
  status: string;
  sent_at: string;
}

interface LinhaUsuario {
  user_id: number;
  email: string;
  nome: string | null;
  plan_status: string;
  page_count: number;
  segmento: string;
  email_opt_out: boolean;
  created_at: string | null;
  last_activity_at: string | null;
  total_emails: number;
  ultimo_email: UltimoEmail | null;
}

interface EventoHistorico {
  id: number;
  tipo: string;
  rotulo: string;
  status: string;
  sent_at: string;
  assunto: string | null;
  cupom: string | null;
  validade: string | null;
  erro: string | null;
}

const FILTROS = [
  { id: "todos", label: "Todos" },
  { id: "S1", label: "S1 · Esgotou" },
  { id: "S2", label: "S2 · Quase no fim" },
  { id: "S3", label: "S3 · Usou parte" },
  { id: "S4", label: "S4 · Nunca usou" },
  { id: "assinante", label: "Assinantes" },
  { id: "ex-assinante", label: "Ex-assinantes" },
];

function badgeSegmento(seg: string): string {
  if (seg.startsWith("S1")) return "bg-orange-500/10 text-orange-400 border-orange-500/30";
  if (seg.startsWith("S2")) return "bg-amber-500/10 text-amber-400 border-amber-500/30";
  if (seg.startsWith("S3")) return "bg-blue-500/10 text-blue-400 border-blue-500/30";
  if (seg.startsWith("S4")) return "bg-slate-500/10 text-slate-400 border-slate-500/30";
  if (seg === "assinante") return "bg-emerald-500/10 text-emerald-400 border-emerald-500/30";
  if (seg === "ex-assinante" || seg === "pgto pendente")
    return "bg-red-500/10 text-red-400 border-red-500/30";
  return "bg-muted/30 text-muted-foreground border-border/50";
}

function quando(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const horas = (Date.now() - d.getTime()) / 3600000;
  if (horas < 1) return "agora há pouco";
  if (horas < 24) return `há ${Math.floor(horas)}h`;
  const dias = Math.floor(horas / 24);
  if (dias < 30) return `há ${dias}d`;
  return d.toLocaleDateString("pt-BR");
}

export default function AdminEmailsTab() {
  const [linhas, setLinhas] = useState<LinhaUsuario[]>([]);
  const [porTipo, setPorTipo] = useState<{ rotulo: string; total: number }[]>([]);
  const [totais, setTotais] = useState({ emails: 0, falhas: 0 });
  const [filtro, setFiltro] = useState("todos");
  const [busca, setBusca] = useState("");
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const [aberto, setAberto] = useState<LinhaUsuario | null>(null);
  const [historico, setHistorico] = useState<EventoHistorico[]>([]);
  const [carregandoHist, setCarregandoHist] = useState(false);

  const buscar = useCallback(async () => {
    setCarregando(true);
    setErro(null);
    try {
      const token = localStorage.getItem("access_token");
      const res = await fetch(`${API_BASE_URL}/api/admin/email-events`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        setErro(
          res.status === 403
            ? "Acesso restrito a administradores."
            : `Erro ${res.status} ao carregar.`
        );
        return;
      }
      const d = await res.json();
      setLinhas(d.usuarios || []);
      setPorTipo(d.por_tipo || []);
      setTotais({ emails: d.total_emails || 0, falhas: d.falhas || 0 });
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => { buscar(); }, [buscar]);

  const abrirHistorico = async (u: LinhaUsuario) => {
    setAberto(u);
    setHistorico([]);
    setCarregandoHist(true);
    try {
      const token = localStorage.getItem("access_token");
      const res = await fetch(
        `${API_BASE_URL}/api/admin/email-events/${u.user_id}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.ok) {
        const d = await res.json();
        setHistorico(d.historico || []);
      }
    } finally {
      setCarregandoHist(false);
    }
  };

  const visiveis = linhas.filter((u) => {
    if (busca && !u.email.toLowerCase().includes(busca.toLowerCase())) return false;
    if (filtro === "todos") return true;
    return u.segmento.toLowerCase().includes(filtro.toLowerCase());
  });

  const descadastrados = linhas.filter((u) => u.email_opt_out).length;

  return (
    <div className="space-y-6">

      {/* Cards de resumo */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-xl border border-border/50 bg-card/30 p-6 text-center">
          <div className="text-sm text-muted-foreground mb-2">Usuários</div>
          <div className="text-4xl font-bold">{linhas.length}</div>
        </div>
        <div className="rounded-xl border border-border/50 bg-card/30 p-6 text-center">
          <div className="text-sm text-muted-foreground mb-2">E-mails enviados</div>
          <div className="text-4xl font-bold text-blue-400">{totais.emails}</div>
        </div>
        <div className="rounded-xl border border-border/50 bg-card/30 p-6 text-center">
          <div className="text-sm text-muted-foreground mb-2">Falhas</div>
          <div className={`text-4xl font-bold ${totais.falhas > 0 ? "text-red-400" : "text-emerald-400"}`}>
            {totais.falhas}
          </div>
        </div>
        <div className="rounded-xl border border-border/50 bg-card/30 p-6 text-center">
          <div className="text-sm text-muted-foreground mb-2">Descadastrados</div>
          <div className="text-4xl font-bold text-amber-400">{descadastrados}</div>
        </div>
      </div>

      {/* Busca + refresh */}
      <div className="rounded-xl border border-border/50 bg-card/30 p-4 flex gap-3 items-center flex-wrap">
        <div className="relative flex-1 min-w-[220px]">
          <i className="ti ti-search absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground text-sm" />
          <input
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar por e-mail..."
            className="w-full pl-10 pr-4 py-2.5 rounded-lg bg-background/50 border border-border/50 text-sm outline-none focus:border-primary/50 transition-colors"
          />
        </div>
        <button
          onClick={buscar}
          className="p-2.5 rounded-lg border border-border/50 text-muted-foreground hover:text-foreground hover:border-border transition-all"
          title="Atualizar"
        >
          <i className="ti ti-refresh" />
        </button>
      </div>

      {/* Filtros por segmento */}
      <div className="flex gap-2 flex-wrap">
        {FILTROS.map((f) => (
          <button
            key={f.id}
            onClick={() => setFiltro(f.id)}
            className={`px-3.5 py-2 rounded-lg text-xs font-semibold border transition-all ${
              filtro === f.id
                ? "bg-primary text-primary-foreground border-primary"
                : "border-border/50 text-muted-foreground hover:text-foreground hover:border-border"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {erro && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
          {erro}
        </div>
      )}

      {/* Tabela */}
      {carregando ? (
        <div className="rounded-xl border border-border/50 bg-card/30 py-20 text-center text-muted-foreground">
          <i className="ti ti-loader-2 animate-spin text-2xl" />
          <div className="mt-3 text-sm">Carregando...</div>
        </div>
      ) : (
        <div className="rounded-xl border border-border/50 bg-card/30 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[840px]">
              <thead>
                <tr className="border-b border-border/50">
                  <th className="text-left px-5 py-4 text-xs uppercase tracking-wider text-muted-foreground font-semibold">ID</th>
                  <th className="text-left px-5 py-4 text-xs uppercase tracking-wider text-muted-foreground font-semibold">E-mail</th>
                  <th className="text-left px-5 py-4 text-xs uppercase tracking-wider text-muted-foreground font-semibold">Segmento</th>
                  <th className="text-left px-5 py-4 text-xs uppercase tracking-wider text-muted-foreground font-semibold">Páginas</th>
                  <th className="text-left px-5 py-4 text-xs uppercase tracking-wider text-muted-foreground font-semibold">Último e-mail</th>
                  <th className="text-left px-5 py-4 text-xs uppercase tracking-wider text-muted-foreground font-semibold">Total</th>
                  <th className="px-5 py-4" />
                </tr>
              </thead>
              <tbody>
                {visiveis.map((u) => (
                  <tr
                    key={u.user_id}
                    onClick={() => abrirHistorico(u)}
                    className="border-b border-border/30 last:border-0 hover:bg-muted/20 cursor-pointer transition-colors"
                  >
                    <td className="px-5 py-4 text-muted-foreground text-xs">{u.user_id}</td>
                    <td className="px-5 py-4">
                      <div className="font-medium text-blue-400">{u.email}</div>
                      {u.nome && (
                        <div className="text-xs text-muted-foreground mt-0.5">{u.nome}</div>
                      )}
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex gap-1.5 items-center flex-wrap">
                        <span className={`px-2.5 py-1 rounded-md text-xs font-medium border whitespace-nowrap ${badgeSegmento(u.segmento)}`}>
                          {u.segmento}
                        </span>
                        {u.email_opt_out && (
                          <span className="px-2 py-1 rounded-md text-xs border bg-red-500/10 text-red-400 border-red-500/30">
                            opt-out
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-4 font-semibold">{u.page_count}</td>
                    <td className="px-5 py-4">
                      {u.ultimo_email ? (
                        <>
                          <div className={u.ultimo_email.status === "failed" ? "text-red-400" : ""}>
                            {u.ultimo_email.rotulo}
                          </div>
                          <div className="text-xs text-muted-foreground mt-0.5">
                            {quando(u.ultimo_email.sent_at)}
                            {u.ultimo_email.status === "failed" && " · falhou"}
                          </div>
                        </>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="px-5 py-4 text-muted-foreground">{u.total_emails}</td>
                    <td className="px-5 py-4 text-right text-muted-foreground">
                      <i className="ti ti-chevron-right" />
                    </td>
                  </tr>
                ))}
                {visiveis.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-5 py-16 text-center text-muted-foreground">
                      Nenhum usuário neste filtro.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Enviados por tipo */}
      {porTipo.length > 0 && (
        <div className="rounded-xl border border-border/50 bg-card/30 p-5">
          <h3 className="text-xs uppercase tracking-wider text-muted-foreground font-semibold mb-4">
            Enviados por tipo
          </h3>
          <div className="flex gap-2 flex-wrap">
            {porTipo.map((t) => (
              <div
                key={t.rotulo}
                className="rounded-lg border border-border/50 bg-background/40 px-3.5 py-2 text-xs"
              >
                <span className="text-muted-foreground">{t.rotulo}</span>
                <span className="ml-2 font-bold text-blue-400">{t.total}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Modal de histórico */}
      {aberto && (
        <div
          className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50"
          onClick={() => setAberto(null)}
        >
          <div
            className="bg-card border border-border rounded-xl max-w-2xl w-full max-h-[80vh] overflow-hidden flex flex-col shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 p-5 border-b border-border/50">
              <div className="min-w-0 flex-1">
                <div className="font-semibold truncate text-blue-400">{aberto.email}</div>
                <div className="text-xs text-muted-foreground mt-1">
                  {aberto.segmento} · {aberto.page_count} páginas · última atividade{" "}
                  {quando(aberto.last_activity_at)}
                </div>
              </div>
              <button
                onClick={() => setAberto(null)}
                className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/30 transition-all"
              >
                <i className="ti ti-x" />
              </button>
            </div>

            <div className="overflow-y-auto p-5">
              {carregandoHist ? (
                <div className="text-center py-10 text-muted-foreground">
                  <i className="ti ti-loader-2 animate-spin text-xl" />
                </div>
              ) : historico.length === 0 ? (
                <div className="text-center py-10 text-muted-foreground text-sm">
                  Nenhum e-mail enviado para este usuário ainda.
                </div>
              ) : (
                <div className="space-y-4">
                  {historico.map((h) => (
                    <div key={h.id} className="flex gap-3 pb-4 border-b border-border/30 last:border-0 last:pb-0">
                      <div
                        className={`w-7 h-7 rounded-full flex items-center justify-center text-xs shrink-0 ${
                          h.status === "sent"
                            ? "bg-emerald-500/15 text-emerald-400"
                            : "bg-red-500/15 text-red-400"
                        }`}
                      >
                        <i className={h.status === "sent" ? "ti ti-check" : "ti ti-x"} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="font-medium">{h.rotulo}</div>
                        {h.assunto && (
                          <div className="text-xs text-muted-foreground mt-1 truncate">
                            {h.assunto}
                          </div>
                        )}
                        {h.cupom && (
                          <div className="text-xs mt-1.5 font-mono text-amber-400">
                            {h.cupom}
                            {h.validade && ` · até ${h.validade}`}
                          </div>
                        )}
                        {h.erro && <div className="text-xs mt-1.5 text-red-400">{h.erro}</div>}
                      </div>
                      <div className="text-xs text-muted-foreground shrink-0 text-right">
                        {new Date(h.sent_at).toLocaleString("pt-BR", {
                          day: "2-digit",
                          month: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
