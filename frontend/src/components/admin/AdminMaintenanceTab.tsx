// frontend/src/components/admin/AdminMaintenanceTab.tsx
//
// Aba "Manutenções" do painel admin.
// - Lista todas as janelas (passadas, atuais, futuras)
// - Botão "Programar manutenção"
// - Botão "Manutenção emergencial"
// - Painel ao vivo se houver manutenção ativa

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Wrench, Plus, Zap, Loader2, Edit2, Trash2, AlertTriangle,
  Calendar, Megaphone, Clock, CheckCircle2, XCircle, Power,
} from "lucide-react";
import { toast } from "sonner";
import MaintenanceFormModal from "./MaintenanceFormModal";
import MaintenanceEmergencyModal from "./MaintenanceEmergencyModal";
import MaintenanceLiveDashboard from "./MaintenanceLiveDashboard";

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

export interface MaintenanceWindow {
  id: number;
  announcement_id: number | null;
  starts_at: string;
  ends_at: string;
  actually_ended_at: string | null;
  message: string;
  status: "scheduled" | "active" | "completed" | "cancelled";
  is_emergency: boolean;
  created_at: string;
  updated_at: string;
  created_by_admin: string | null;
  announcement?: {
    id: number;
    title: string;
    active: boolean;
    starts_at: string | null;
    ends_at: string | null;
  };
}

interface SummaryStats {
  total: number;
  active: number;
  scheduled: number;
  completed: number;
  cancelled: number;
}

const STATUS_META: Record<MaintenanceWindow["status"], {
  label: string;
  cls: string;
  icon: typeof Clock;
}> = {
  scheduled: { label: "Agendada",  cls: "bg-blue-500/15 text-blue-600 dark:text-blue-400",       icon: Calendar },
  active:    { label: "EM CURSO",  cls: "bg-red-500/15 text-red-600 dark:text-red-400",          icon: Power    },
  completed: { label: "Concluída", cls: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400", icon: CheckCircle2 },
  cancelled: { label: "Cancelada", cls: "bg-muted text-muted-foreground",                       icon: XCircle  },
};

const AdminMaintenanceTab = () => {
  const [items, setItems] = useState<MaintenanceWindow[]>([]);
  const [stats, setStats] = useState<SummaryStats | null>(null);
  const [activeMaint, setActiveMaint] = useState<MaintenanceWindow | null>(null);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const [showSchedule, setShowSchedule] = useState(false);
  const [showEmergency, setShowEmergency] = useState(false);
  const [editing, setEditing] = useState<MaintenanceWindow | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== "all") params.set("status", statusFilter);
      const res = await adminFetch(`/api/admin/maintenance?${params}`);
      const data = await res.json();
      if (res.ok) {
        setItems(data.items || []);
        setStats(data.stats || null);
        // Identifica a ativa
        const active = (data.items || []).find(
          (m: MaintenanceWindow) => m.status === "active"
        );
        setActiveMaint(active || null);
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

  // Auto-refresh a cada 30s se há manutenção ativa
  useEffect(() => {
    if (!activeMaint) return;
    const t = setInterval(() => fetchData(), 30000);
    return () => clearInterval(t);
  }, [activeMaint, fetchData]);

  const handleDelete = async (m: MaintenanceWindow) => {
    if (!confirm(`Excluir manutenção agendada para ${formatDateRange(m)}?`)) return;
    try {
      const res = await adminFetch(`/api/admin/maintenance/${m.id}`, {
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

  return (
    <div className="space-y-4">
      {/* Cabeçalho */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-semibold text-foreground flex items-center gap-2">
            <Wrench className="w-5 h-5 text-primary" />
            Manutenções
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Programe janelas de manutenção. Durante a manutenção, o sistema fica bloqueado para usuários.
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => setShowEmergency(true)}
            className="bg-red-500/10 border border-red-500/30 text-red-600 dark:text-red-400 px-4 py-2 rounded-md text-sm font-semibold flex items-center gap-2 hover:bg-red-500/20 transition"
          >
            <Zap className="w-4 h-4" />
            Manutenção emergencial
          </button>
          <button
            onClick={() => { setEditing(null); setShowSchedule(true); }}
            className="gradient-primary text-primary-foreground px-4 py-2 rounded-md text-sm font-semibold flex items-center gap-2 hover:opacity-90 transition"
          >
            <Plus className="w-4 h-4" />
            Programar manutenção
          </button>
        </div>
      </div>

      {/* Painel ao vivo se há manutenção ativa */}
      {activeMaint && (
        <MaintenanceLiveDashboard
          maintenance={activeMaint}
          onUpdate={fetchData}
        />
      )}

      {/* Stats agregados */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <StatCard label="Total"      value={stats.total} />
          <StatCard label="Ativas"     value={stats.active}    cls="text-red-600 dark:text-red-400" />
          <StatCard label="Agendadas"  value={stats.scheduled} cls="text-blue-600 dark:text-blue-400" />
          <StatCard label="Concluídas" value={stats.completed} cls="text-emerald-600 dark:text-emerald-400" />
          <StatCard label="Canceladas" value={stats.cancelled} />
        </div>
      )}

      {/* Filtros */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-muted-foreground">Filtrar:</span>
        {(["all", "active", "scheduled", "completed", "cancelled"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setStatusFilter(f)}
            className={`text-xs px-3 py-1 rounded-full border transition ${
              statusFilter === f
                ? "border-primary bg-primary/10 text-primary"
                : "border-border/50 text-muted-foreground hover:bg-muted/50"
            }`}
          >
            {f === "all"        ? "Todas"      :
             f === "active"     ? "Ativas"     :
             f === "scheduled"  ? "Agendadas"  :
             f === "completed"  ? "Concluídas" :
                                  "Canceladas"}
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
            <Wrench className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
            <p className="text-sm text-muted-foreground">
              Nenhuma manutenção encontrada.
            </p>
          </div>
        ) : (
          items.map((m, i) => {
            const meta = STATUS_META[m.status];
            const Icon = meta.icon;
            return (
              <motion.div
                key={m.id}
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03 }}
                className={`glass-card p-4 ${m.status === "active" ? "border-red-500/30" : ""}`}
              >
                <div className="flex items-start gap-3">
                  <div className={`w-9 h-9 rounded-lg ${meta.cls} flex items-center justify-center shrink-0`}>
                    <Icon className="w-4 h-4" />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded ${meta.cls}`}>
                        {meta.label}
                      </span>
                      {m.is_emergency && (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-red-500/15 text-red-600 dark:text-red-400 inline-flex items-center gap-1">
                          <Zap className="w-3 h-3" />
                          Emergencial
                        </span>
                      )}
                      {m.announcement && (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-blue-500/15 text-blue-600 dark:text-blue-400 inline-flex items-center gap-1">
                          <Megaphone className="w-3 h-3" />
                          Aviso prévio
                        </span>
                      )}
                    </div>

                    <h3 className="text-sm font-semibold text-foreground">
                      {formatDateRange(m)}
                    </h3>

                    {m.message && (
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                        {m.message}
                      </p>
                    )}

                    <div className="flex items-center gap-3 mt-2 text-[11px] text-muted-foreground flex-wrap">
                      <span>Duração: {formatDuration(m)}</span>
                      {m.actually_ended_at && (
                        <span>
                          Encerrada em: {formatDate(m.actually_ended_at)}
                        </span>
                      )}
                      {m.created_by_admin && (
                        <span className="opacity-60">
                          por {m.created_by_admin}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Ações */}
                  <div className="flex items-center gap-1 shrink-0">
                    {m.status === "scheduled" && (
                      <>
                        <button
                          onClick={() => { setEditing(m); setShowSchedule(true); }}
                          title="Editar"
                          className="p-2 rounded-md hover:bg-muted/50 text-muted-foreground hover:text-foreground transition"
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(m)}
                          title="Excluir"
                          className="p-2 rounded-md hover:bg-red-500/10 text-muted-foreground hover:text-red-500 transition"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })
        )}
      </div>

      {/* Modais */}
      {showSchedule && (
        <MaintenanceFormModal
          maintenance={editing ?? undefined}
          onClose={() => { setShowSchedule(false); setEditing(null); }}
          onSaved={() => { setShowSchedule(false); setEditing(null); fetchData(); }}
        />
      )}

      {showEmergency && (
        <MaintenanceEmergencyModal
          onClose={() => setShowEmergency(false)}
          onSaved={() => { setShowEmergency(false); fetchData(); }}
        />
      )}
    </div>
  );
};

const StatCard = ({
  label, value, cls,
}: {
  label: string; value: number; cls?: string;
}) => (
  <div className="glass-card p-3">
    <div className={`text-2xl font-bold ${cls ?? "text-foreground"}`}>{value}</div>
    <div className="text-xs text-muted-foreground">{label}</div>
  </div>
);

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch { return "—"; }
}

function formatDateRange(m: MaintenanceWindow): string {
  return `${formatDate(m.starts_at)} → ${formatDate(m.ends_at)}`;
}

function formatDuration(m: MaintenanceWindow): string {
  try {
    const start = new Date(m.starts_at);
    const end = new Date(m.actually_ended_at || m.ends_at);
    const minutes = Math.round((end.getTime() - start.getTime()) / 60000);
    if (minutes < 60) return `${minutes} min`;
    const h = Math.floor(minutes / 60);
    const min = minutes % 60;
    return `${h}h${min > 0 ? ` ${min}min` : ""}`;
  } catch { return "—"; }
}

export default AdminMaintenanceTab;
