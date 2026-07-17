import { useEffect, useState } from "react";
import { History, X, Loader2 } from "lucide-react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function getToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("jwt_token");
}

interface HistoryRow {
  month: string;
  label: string;
  plan_status: string;
  plan_label: string;
  pages_used: number;
  pages_included: number;
  extras: number;
  in_progress: boolean;
}

interface Props {
  user: { id: number; email: string };
  onClose: () => void;
}

const PLAN_PILL: Record<string, string> = {
  premium: "bg-primary/15 text-primary",
  standard: "bg-emerald-500/15 text-emerald-500",
  basic: "bg-blue-500/15 text-blue-500",
  free: "bg-muted text-muted-foreground",
};

export default function UserHistoryModal({ user, onClose }: Props) {
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/admin/users/${user.id}/usage-history`, {
          headers: { Authorization: `Bearer ${getToken()}` },
        });
        const data = await res.json();
        if (res.ok) setRows(data.history || []);
        else setError(data.msg || "Erro ao carregar historico.");
      } catch {
        setError("Erro de rede.");
      } finally {
        setLoading(false);
      }
    })();
  }, [user.id]);

  const maxUsed = Math.max(1, ...rows.map((r) => r.pages_used));
  const chart = [...rows].reverse();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-xl bg-card border border-border/50 rounded-2xl overflow-hidden shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-border/50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-primary/15 flex items-center justify-center">
              <History className="w-4 h-4 text-primary" />
            </div>
            <div>
              <h3 className="text-foreground font-medium text-base leading-tight">Historico de uso</h3>
              <p className="text-muted-foreground text-xs">{user.email}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all">
            <X className="w-4 h-4" />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : error ? (
          <div className="px-5 py-10 text-center text-sm text-red-500">{error}</div>
        ) : rows.length === 0 ? (
          <div className="px-5 py-10 text-center text-sm text-muted-foreground">Nenhum registro de uso ainda.</div>
        ) : (
          <>
            <div className="px-5 pt-4">
              <div className="flex items-end gap-1.5 h-24">
                {chart.map((r) => (
                  <div key={r.month} className="flex-1 flex flex-col items-center gap-1.5">
                    <div
                      className={`w-full rounded-t ${r.in_progress ? "bg-primary" : "bg-primary/40"}`}
                      style={{ height: `${Math.max(4, (r.pages_used / maxUsed) * 72)}px` }}
                      title={`${r.pages_used} paginas`}
                    />
                    <span className={`text-[10px] ${r.in_progress ? "text-foreground" : "text-muted-foreground"}`}>
                      {r.label.split("/")[0]}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="px-5 py-4 max-h-80 overflow-y-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted-foreground text-xs">
                    <th className="text-left font-medium pb-2">Mes</th>
                    <th className="text-left font-medium pb-2">Plano</th>
                    <th className="text-right font-medium pb-2">Usadas</th>
                    <th className="text-right font-medium pb-2">Incl.</th>
                    <th className="text-right font-medium pb-2">Extras</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.month} className="border-t border-border/40">
                      <td className="py-2.5 text-foreground">
                        {r.label}
                        {r.in_progress && (
                          <span className="ml-2 text-[10px] text-primary bg-primary/15 px-1.5 py-0.5 rounded">em andamento</span>
                        )}
                      </td>
                      <td className="py-2.5">
                        <span className={`text-xs px-2 py-0.5 rounded-md ${PLAN_PILL[r.plan_status] || "bg-muted text-muted-foreground"}`}>
                          {r.plan_label}
                        </span>
                      </td>
                      <td className="py-2.5 text-right text-foreground">{r.pages_used.toLocaleString("pt-BR")}</td>
                      <td className="py-2.5 text-right text-muted-foreground">{r.pages_included.toLocaleString("pt-BR")}</td>
                      <td className={`py-2.5 text-right ${r.extras > 0 ? "text-amber-500" : "text-muted-foreground"}`}>
                        {r.extras > 0 ? r.extras.toLocaleString("pt-BR") : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
