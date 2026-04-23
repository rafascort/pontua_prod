// frontend/src/components/admin/AdminPromotionsTab.tsx
//
// Aba de gerenciamento de promoções no painel admin.
// CRUD completo + toggle rápido + preview ao vivo no formulário.

import { useState, useEffect, useCallback } from "react";
import {
  Plus, Loader2, Edit3, Trash2, Play, Pause,
  Eye, MousePointerClick, Calendar, AlertTriangle,
  TrendingUp, Archive, Clock,
} from "lucide-react";
import { toast } from "sonner";
import PromotionFormModal from "./PromotionFormModal";
import type { Promotion } from "@/hooks/usePromotions";

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

interface PromotionFull extends Promotion {
  impressions?: number;
  clicks?: number;
  click_rate?: number;
}

interface SummaryStats {
  total: number;
  live: number;
  scheduled: number;
  expired: number;
  inactive: number;
}

const AdminPromotionsTab = () => {
  const [items, setItems] = useState<PromotionFull[]>([]);
  const [stats, setStats] = useState<SummaryStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState("all");

  const [showCreate, setShowCreate] = useState(false);
  const [editItem, setEditItem] = useState<PromotionFull | null>(null);
  const [deleteItem, setDeleteItem] = useState<PromotionFull | null>(null);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== "all") params.set("status", statusFilter);
      const res = await adminFetch(`/api/admin/promotions?${params}`);
      const data = await res.json();
      if (res.ok) {
        setItems(data.items || []);
        setStats(data.stats || null);
      } else {
        toast.error(data.msg || "Erro ao carregar promoções.");
      }
    } catch {
      toast.error("Erro de rede.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const handleToggle = async (id: number) => {
    try {
      const res = await adminFetch(`/api/admin/promotions/${id}/toggle`, {
        method: "PATCH",
      });
      const data = await res.json();
      if (res.ok) {
        toast.success(data.msg);
        fetchItems();
      } else {
        toast.error(data.msg);
      }
    } catch {
      toast.error("Erro de rede.");
    }
  };

  const handleDelete = async () => {
    if (!deleteItem) return;
    try {
      const res = await adminFetch(`/api/admin/promotions/${deleteItem.id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        toast.success("Promoção excluída.");
        setDeleteItem(null);
        fetchItems();
      } else {
        const data = await res.json();
        toast.error(data.msg);
      }
    } catch {
      toast.error("Erro de rede.");
    }
  };

  return (
    <div>
      {/* Métricas */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
          <StatCard
            label="Total"
            value={String(stats.total)}
            icon={<Archive className="w-4 h-4 text-muted-foreground" />}
          />
          <StatCard
            label="Ativas agora"
            value={String(stats.live)}
            highlight="text-emerald-600 dark:text-emerald-400"
            icon={<Play className="w-4 h-4 text-emerald-500" />}
          />
          <StatCard
            label="Agendadas"
            value={String(stats.scheduled)}
            highlight="text-amber-600 dark:text-amber-400"
            icon={<Clock className="w-4 h-4 text-amber-500" />}
          />
          <StatCard
            label="Expiradas"
            value={String(stats.expired)}
            icon={<Archive className="w-4 h-4 text-muted-foreground" />}
          />
          <StatCard
            label="Pausadas"
            value={String(stats.inactive)}
            icon={<Pause className="w-4 h-4 text-muted-foreground" />}
          />
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between gap-3 mb-4">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 text-sm rounded-md bg-background border border-border/50 focus:border-primary outline-none"
        >
          <option value="all">Todas</option>
          <option value="live">Ativas agora</option>
          <option value="scheduled">Agendadas</option>
          <option value="expired">Expiradas</option>
          <option value="inactive">Pausadas</option>
        </select>

        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-md bg-foreground text-background hover:opacity-90"
        >
          <Plus className="w-4 h-4" />
          Nova promoção
        </button>
      </div>

      {/* Lista */}
      {loading ? (
        <div className="p-12 flex justify-center">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      ) : items.length === 0 ? (
        <div className="glass-card p-12 text-center">
          <Archive className="w-8 h-8 text-muted-foreground/40 mx-auto mb-3" />
          <p className="text-muted-foreground">Nenhuma promoção encontrada.</p>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-4 text-sm text-primary hover:underline"
          >
            Criar primeira promoção →
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((p) => (
            <PromotionListItem
              key={p.id}
              promotion={p}
              onEdit={() => setEditItem(p)}
              onToggle={() => handleToggle(p.id)}
              onDelete={() => setDeleteItem(p)}
            />
          ))}
        </div>
      )}

      {/* Modais */}
      {showCreate && (
        <PromotionFormModal
          onClose={() => setShowCreate(false)}
          onSaved={() => {
            setShowCreate(false);
            fetchItems();
          }}
        />
      )}

      {editItem && (
        <PromotionFormModal
          promotion={editItem}
          onClose={() => setEditItem(null)}
          onSaved={() => {
            setEditItem(null);
            fetchItems();
          }}
        />
      )}

      {deleteItem && (
        <div
          className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setDeleteItem(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-card rounded-2xl w-full max-w-md p-6"
          >
            <div className="flex items-start gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-destructive/15 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5 text-destructive" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-foreground">
                  Excluir promoção?
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                  "{deleteItem.title}" será removida. As métricas coletadas
                  também serão apagadas. Esta ação é irreversível.
                </p>
              </div>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => setDeleteItem(null)}
                className="flex-1 px-4 py-2 text-sm font-medium rounded-md border border-border/50 hover:bg-muted/50"
              >
                Cancelar
              </button>
              <button
                onClick={handleDelete}
                className="flex-1 px-4 py-2 text-sm font-medium rounded-md bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                Excluir
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ─── Subcomponentes ─────────────────────────────────────────────────────

function PromotionListItem({
  promotion: p, onEdit, onToggle, onDelete,
}: {
  promotion: PromotionFull;
  onEdit: () => void;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const statusConfig: Record<string, { cls: string; label: string; dotCls: string }> = {
    live: {
      cls: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
      label: "Ativa",
      dotCls: "bg-emerald-500",
    },
    scheduled: {
      cls: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
      label: "Agendada",
      dotCls: "bg-amber-500",
    },
    expired: {
      cls: "bg-muted text-muted-foreground",
      label: "Expirada",
      dotCls: "bg-muted-foreground",
    },
    inactive: {
      cls: "bg-muted text-muted-foreground",
      label: "Pausada",
      dotCls: "bg-muted-foreground",
    },
  };

  const status = statusConfig[p.status] ?? statusConfig.inactive;

  const fmtDate = (iso: string | null) => {
    if (!iso) return null;
    try {
      return new Date(iso).toLocaleDateString("pt-BR", {
        day: "2-digit",
        month: "short",
      });
    } catch {
      return null;
    }
  };

  return (
    <div className="glass-card p-4">
      <div className="flex items-start gap-3">
        {/* Status dot */}
        <div className="pt-1">
          <div className={`w-2 h-2 rounded-full ${status.dotCls}`} />
        </div>

        {/* Conteúdo */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3 mb-2">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <span className="text-[11px] font-medium px-1.5 py-0.5 rounded bg-muted">
                  {p.badge_label}
                </span>
                <span className={`text-[11px] font-semibold px-1.5 py-0.5 rounded ${status.cls}`}>
                  {status.label}
                </span>
                {p.discount_hint && (
                  <span className="text-xs text-muted-foreground">
                    {p.discount_hint}
                  </span>
                )}
              </div>
              <h4 className="font-semibold text-foreground truncate">{p.title}</h4>
              <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                {p.description}
              </p>
            </div>

            {/* Ações */}
            <div className="flex items-center gap-1 shrink-0">
              <button
                onClick={onToggle}
                title={p.active ? "Pausar" : "Ativar"}
                className="p-1.5 rounded hover:bg-muted/50 text-muted-foreground hover:text-foreground transition"
              >
                {p.active ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
              </button>
              <button
                onClick={onEdit}
                title="Editar"
                className="p-1.5 rounded hover:bg-muted/50 text-muted-foreground hover:text-foreground transition"
              >
                <Edit3 className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={onDelete}
                title="Excluir"
                className="p-1.5 rounded hover:bg-destructive/15 text-muted-foreground hover:text-destructive transition"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Métricas + datas */}
          <div className="flex items-center gap-4 text-xs text-muted-foreground flex-wrap">
            <div className="flex items-center gap-1">
              <Eye className="w-3 h-3" />
              {p.impressions ?? 0} impressões
            </div>
            <div className="flex items-center gap-1">
              <MousePointerClick className="w-3 h-3" />
              {p.clicks ?? 0} cliques
            </div>
            {p.click_rate !== undefined && p.click_rate > 0 && (
              <div className="flex items-center gap-1">
                <TrendingUp className="w-3 h-3" />
                {p.click_rate}% CTR
              </div>
            )}
            {(p.starts_at || p.ends_at) && (
              <div className="flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                {fmtDate(p.starts_at) || "Desde início"}
                {" → "}
                {fmtDate(p.ends_at) || "Sem fim"}
              </div>
            )}
            <div className="ml-auto opacity-70">
              Prioridade {p.priority}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  label, value, icon, highlight,
}: { label: string; value: string; icon?: React.ReactNode; highlight?: string }) {
  return (
    <div className="bg-muted/30 rounded-lg p-3">
      <div className="flex items-center gap-1.5 mb-1">
        {icon}
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
      <div className={`text-xl font-bold ${highlight ?? "text-foreground"}`}>
        {value}
      </div>
    </div>
  );
}

export default AdminPromotionsTab;
