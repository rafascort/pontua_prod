// frontend/src/components/admin/AdminAnnouncementsTab.tsx
//
// Aba "Avisos" do painel admin. Lista todos os avisos com stats, filtros e ações.

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Megaphone, Plus, Edit2, Trash2, Pause, Play, Eye,
  Loader2, Info, AlertTriangle, AlertOctagon, Sparkles,
} from "lucide-react";
import { toast } from "sonner";
import AnnouncementFormModal from "./AnnouncementFormModal";
import AnnouncementAcksModal from "./AnnouncementAcksModal";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function getToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("jwt_token");
}

async function adminFetch(url: string, options: RequestInit = {}) {
  const token = getToken();
  const res = await fetch(`${API_BASE_URL}${url}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    },
  });
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Sessão expirada.");
  }
  return res;
}

export interface AdminAnnouncement {
  id: number;
  title: string;
  message: string;
  severity: "info" | "warning" | "critical" | "news";
  frequency: "once" | "every_session";
  priority: number;
  active: boolean;
  starts_at: string | null;
  ends_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  status: "live" | "scheduled" | "expired" | "inactive";
  total_users?: number;
  unique_acks?: number;
  pending_count?: number;
  ack_rate_pct?: number;
}

interface SummaryStats {
  total: number;
  live: number;
  scheduled: number;
  expired: number;
  inactive: number;
}

const SEVERITY_META: Record<AdminAnnouncement["severity"], {
  icon: typeof Info;
  label: string;
  cls: string;
}> = {
  info:     { icon: Info,          label: "Info",     cls: "bg-blue-500/15 text-blue-600 dark:text-blue-400" },
  warning:  { icon: AlertTriangle, label: "Aviso",    cls: "bg-amber-500/15 text-amber-600 dark:text-amber-400" },
  critical: { icon: AlertOctagon,  label: "Crítico",  cls: "bg-red-500/15 text-red-600 dark:text-red-400" },
  news:     { icon: Sparkles,      label: "Novidade", cls: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400" },
};

const STATUS_META: Record<AdminAnnouncement["status"], { label: string; cls: string }> = {
  live:      { label: "No ar",     cls: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400" },
  scheduled: { label: "Agendado",  cls: "bg-blue-500/15 text-blue-600 dark:text-blue-400" },
  expired:   { label: "Expirado",  cls: "bg-muted text-muted-foreground" },
  inactive:  { label: "Pausado",   cls: "bg-amber-500/15 text-amber-600 dark:text-amber-400" },
};

const AdminAnnouncementsTab = () => {
  const [items, setItems] = useState<AdminAnnouncement[]>([]);
  const [stats, setStats] = useState<SummaryStats | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [loading, setLoading] = useState(false);

  const [editingItem, setEditingItem] = useState<AdminAnnouncement | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [acksItem, setAcksItem] = useState<AdminAnnouncement | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== "all") params.set("status", statusFilter);
      const res = await adminFetch(`/api/admin/announcements?${params}`);
      const data = await res.json();
      if (res.ok) {
        setItems(data.items || []);
        setStats(data.stats || null);
      } else {
        toast.error(data.msg || "Erro ao carregar avisos.");
      }
    } catch {
      toast.error("Erro de rede.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleToggle = async (a: AdminAnnouncement) => {
    try {
      const res = await adminFetch(
        `/api/admin/announcements/${a.id}/toggle`,
        { method: "PATCH" }
      );
      const data = await res.json();
      if (res.ok) {
        toast.success(data.msg);
        fetchData();
      } else {
        toast.error(data.msg);
      }
    } catch {
      toast.error("Erro de rede.");
    }
  };

  const handleDelete = async (a: AdminAnnouncement) => {
    if (!confirm(`Excluir aviso "${a.title}"?\n\nEssa ação não pode ser desfeita.`)) {
      return;
    }
    try {
      const res = await adminFetch(`/api/admin/announcements/${a.id}`, {
        method: "DELETE",
      });
      const data = await res.json();
      if (res.ok) {
        toast.success(data.msg);
        fetchData();
      } else {
        toast.error(data.msg);
      }
    } catch {
      toast.error("Erro de rede.");
    }
  };

  const formatDateRange = (a: AdminAnnouncement) => {
    if (!a.starts_at && !a.ends_at) return "Sem janela definida";
    const fmt = (iso: string | null) => {
      if (!iso) return "—";
      try {
        return new Date(iso).toLocaleString("pt-BR", {
          day: "2-digit", month: "2-digit", year: "numeric",
          hour: "2-digit", minute: "2-digit",
        });
      } catch { return "—"; }
    };
    return `${fmt(a.starts_at)} → ${fmt(a.ends_at)}`;
  };

  return (
    <div className="space-y-4">
      {/* Cabeçalho */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-semibold text-foreground flex items-center gap-2">
            <Megaphone className="w-5 h-5 text-primary" />
            Avisos do sistema
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Comunicados que aparecem após o login (manutenções, novidades, alertas).
          </p>
        </div>
        <button
          onClick={() => { setEditingItem(null); setFormOpen(true); }}
          className="gradient-primary text-primary-foreground px-4 py-2 rounded-md text-sm font-semibold flex items-center gap-2 hover:opacity-90 transition"
        >
          <Plus className="w-4 h-4" />
          Novo aviso
        </button>
      </div>

      {/* Stats agregados */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <StatCard label="Total" value={stats.total} />
          <StatCard label="No ar" value={stats.live} cls="text-emerald-600 dark:text-emerald-400" />
          <StatCard label="Agendados" value={stats.scheduled} cls="text-blue-600 dark:text-blue-400" />
          <StatCard label="Expirados" value={stats.expired} />
          <StatCard label="Pausados" value={stats.inactive} cls="text-amber-600 dark:text-amber-400" />
        </div>
      )}

      {/* Filtros */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-muted-foreground">Filtrar:</span>
        {(["all", "live", "scheduled", "expired", "inactive"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setStatusFilter(f)}
            className={`text-xs px-3 py-1 rounded-full border transition ${
              statusFilter === f
                ? "border-primary bg-primary/10 text-primary"
                : "border-border/50 text-muted-foreground hover:bg-muted/50"
            }`}
          >
            {f === "all"        ? "Todos"     :
             f === "live"       ? "No ar"     :
             f === "scheduled"  ? "Agendados" :
             f === "expired"    ? "Expirados" :
                                  "Pausados"}
          </button>
        ))}
      </div>

      {/* Lista */}
      <div className="space-y-2">
        {loading ? (
          <div className="glass-card p-10 flex justify-center">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : items.length === 0 ? (
          <div className="glass-card p-10 text-center">
            <Megaphone className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
            <p className="text-sm text-muted-foreground">
              Nenhum aviso encontrado.
            </p>
          </div>
        ) : (
          items.map((a, i) => {
            const sev = SEVERITY_META[a.severity];
            const st = STATUS_META[a.status];
            const SevIcon = sev.icon;
            return (
              <motion.div
                key={a.id}
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03 }}
                className="glass-card p-4"
              >
                <div className="flex items-start gap-3">
                  {/* Ícone severidade */}
                  <div className={`w-9 h-9 rounded-lg ${sev.cls} flex items-center justify-center shrink-0`}>
                    <SevIcon className="w-4 h-4" />
                  </div>

                  {/* Conteúdo */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded ${sev.cls}`}>
                        {sev.label}
                      </span>
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded ${st.cls}`}>
                        {st.label}
                      </span>
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-muted text-muted-foreground">
                        {a.frequency === "once" ? "1× por usuário" : "Toda sessão"}
                      </span>
                      <span className="text-[10px] text-muted-foreground">
                        Priority: {a.priority}
                      </span>
                    </div>
                    <h3 className="text-sm font-semibold text-foreground truncate">
                      {a.title}
                    </h3>
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                      {a.message}
                    </p>
                    <div className="flex items-center gap-3 mt-2 text-[11px] text-muted-foreground flex-wrap">
                      <span>📅 {formatDateRange(a)}</span>
                      {a.total_users != null && (
                        <span>
                          ✓ {a.unique_acks ?? 0}/{a.total_users}
                          {(a.ack_rate_pct ?? 0) > 0 && ` (${a.ack_rate_pct}%)`}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Ações */}
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => setAcksItem(a)}
                      title="Ver quem confirmou"
                      className="p-2 rounded-md hover:bg-muted/50 text-muted-foreground hover:text-foreground transition"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleToggle(a)}
                      title={a.active ? "Pausar" : "Ativar"}
                      className="p-2 rounded-md hover:bg-muted/50 text-muted-foreground hover:text-foreground transition"
                    >
                      {a.active ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                    </button>
                    <button
                      onClick={() => { setEditingItem(a); setFormOpen(true); }}
                      title="Editar"
                      className="p-2 rounded-md hover:bg-muted/50 text-muted-foreground hover:text-foreground transition"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(a)}
                      title="Excluir"
                      className="p-2 rounded-md hover:bg-red-500/10 text-muted-foreground hover:text-red-500 transition"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </motion.div>
            );
          })
        )}
      </div>

      {/* Modais */}
      {formOpen && (
        <AnnouncementFormModal
          announcement={editingItem ?? undefined}
          onClose={() => setFormOpen(false)}
          onSaved={() => { setFormOpen(false); fetchData(); }}
        />
      )}

      {acksItem && (
        <AnnouncementAcksModal
          announcement={acksItem}
          onClose={() => setAcksItem(null)}
        />
      )}
    </div>
  );
};

const StatCard = ({
  label,
  value,
  cls,
}: {
  label: string;
  value: number;
  cls?: string;
}) => (
  <div className="glass-card p-3">
    <div className={`text-2xl font-bold ${cls ?? "text-foreground"}`}>{value}</div>
    <div className="text-xs text-muted-foreground">{label}</div>
  </div>
);

export default AdminAnnouncementsTab;
