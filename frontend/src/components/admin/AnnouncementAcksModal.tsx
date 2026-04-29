// frontend/src/components/admin/AnnouncementAcksModal.tsx
//
// Modal que mostra quem viu/confirmou um aviso e quem ainda não.

import { useEffect, useState, useCallback } from "react";
import { X, Loader2, CheckCircle2, Clock, Search } from "lucide-react";
import type { AdminAnnouncement } from "./AdminAnnouncementsTab";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function getToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("jwt_token");
}

interface AckItem {
  user_id: number;
  email: string;
  plan_status: string;
  confirmed: boolean;
  last_ack_at: string | null;
  ack_count: number;
}

interface Summary {
  confirmed: number;
  pending: number;
  total_users: number;
}

interface Props {
  announcement: AdminAnnouncement;
  onClose: () => void;
}

const AnnouncementAcksModal = ({ announcement, onClose }: Props) => {
  const [view, setView] = useState<"all" | "confirmed" | "pending">("all");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [items, setItems] = useState<AckItem[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const token = getToken();
      const params = new URLSearchParams({
        view,
        page: String(page),
        per_page: "50",
      });
      if (debouncedSearch) params.set("search", debouncedSearch);

      const res = await fetch(
        `${API_BASE_URL}/api/admin/announcements/${announcement.id}/acks?${params}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const data = await res.json();
      if (res.ok) {
        setItems(data.items || []);
        setSummary(data.summary || null);
        setPages(data.pages || 1);
      }
    } finally {
      setLoading(false);
    }
  }, [announcement.id, view, page, debouncedSearch]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Reset page quando view ou search muda
  useEffect(() => {
    setPage(1);
  }, [view, debouncedSearch]);

  const formatDate = (iso: string | null) => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString("pt-BR", {
        day: "2-digit", month: "2-digit", year: "numeric",
        hour: "2-digit", minute: "2-digit",
      });
    } catch { return "—"; }
  };

  return (
    <div className="fixed inset-0 z-[95] bg-background/85 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-3xl max-h-[90vh] rounded-2xl bg-card border border-border/50 shadow-2xl overflow-hidden flex flex-col">

        {/* Header */}
        <div className="px-6 py-4 border-b border-border/50">
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-lg font-semibold text-foreground line-clamp-1">
              Confirmações: {announcement.title}
            </h2>
            <button
              onClick={onClose}
              className="p-1.5 rounded-md hover:bg-muted/50 text-muted-foreground shrink-0"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          <p className="text-xs text-muted-foreground">
            Visualização de quem confirmou e quem ainda não viu este aviso.
          </p>
        </div>

        {/* Resumo */}
        {summary && (
          <div className="px-6 py-3 border-b border-border/50 grid grid-cols-3 gap-3 text-center">
            <div>
              <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                {summary.confirmed}
              </div>
              <div className="text-xs text-muted-foreground">Confirmaram</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-amber-600 dark:text-amber-400">
                {summary.pending}
              </div>
              <div className="text-xs text-muted-foreground">Pendentes</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-foreground">
                {summary.total_users}
              </div>
              <div className="text-xs text-muted-foreground">Total de usuários</div>
            </div>
          </div>
        )}

        {/* Filtros + busca */}
        <div className="px-6 py-3 border-b border-border/50 flex items-center gap-3 flex-wrap">
          <div className="flex gap-1">
            {(["all", "confirmed", "pending"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`text-xs px-3 py-1 rounded-full border transition ${
                  view === v
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border/50 text-muted-foreground hover:bg-muted/50"
                }`}
              >
                {v === "all" ? "Todos" : v === "confirmed" ? "Confirmaram" : "Pendentes"}
              </button>
            ))}
          </div>

          <div className="flex-1 min-w-[200px] relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por email..."
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-md bg-background border border-border/50 outline-none focus:border-primary"
            />
          </div>
        </div>

        {/* Lista */}
        <div className="flex-1 overflow-y-auto px-6 py-3">
          {loading ? (
            <div className="flex justify-center py-10">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-10 text-sm text-muted-foreground">
              Nenhum usuário encontrado.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/50">
                  <th className="text-left text-[10px] uppercase font-medium text-muted-foreground py-2">
                    Email
                  </th>
                  <th className="text-left text-[10px] uppercase font-medium text-muted-foreground py-2">
                    Status
                  </th>
                  <th className="text-left text-[10px] uppercase font-medium text-muted-foreground py-2">
                    Plano
                  </th>
                  <th className="text-right text-[10px] uppercase font-medium text-muted-foreground py-2">
                    Confirmação
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr
                    key={item.user_id}
                    className="border-b border-border/30 last:border-0"
                  >
                    <td className="py-2.5 text-xs text-foreground">{item.email}</td>
                    <td className="py-2.5">
                      {item.confirmed ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                          <CheckCircle2 className="w-3 h-3" />
                          Confirmado
                          {announcement.frequency === "every_session" && item.ack_count > 1 && (
                            <span className="ml-1 opacity-75">×{item.ack_count}</span>
                          )}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded bg-amber-500/15 text-amber-600 dark:text-amber-400">
                          <Clock className="w-3 h-3" />
                          Pendente
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 text-xs text-muted-foreground capitalize">
                      {item.plan_status}
                    </td>
                    <td className="py-2.5 text-xs text-muted-foreground text-right">
                      {formatDate(item.last_ack_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Paginação */}
        {pages > 1 && (
          <div className="px-6 py-3 border-t border-border/50 flex items-center justify-between text-xs">
            <span className="text-muted-foreground">
              Página {page} de {pages}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page === 1}
                className="px-3 py-1 rounded border border-border/50 disabled:opacity-40 hover:bg-muted/30"
              >
                Anterior
              </button>
              <button
                onClick={() => setPage(Math.min(pages, page + 1))}
                disabled={page === pages}
                className="px-3 py-1 rounded border border-border/50 disabled:opacity-40 hover:bg-muted/30"
              >
                Próxima
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
};

export default AnnouncementAcksModal;
