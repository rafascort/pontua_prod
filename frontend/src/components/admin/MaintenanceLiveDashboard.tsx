// frontend/src/components/admin/MaintenanceLiveDashboard.tsx
//
// Painel ao vivo da manutenção em curso. Mostra tempo decorrido, tempo restante,
// e oferece controles: encerrar antes, estender duração, editar mensagem.

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Power, Loader2, Plus, X, Edit2, Clock, AlertTriangle,
  CheckCircle2,
} from "lucide-react";
import { toast } from "sonner";
import type { MaintenanceWindow } from "./AdminMaintenanceTab";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function getToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("jwt_token");
}

interface Props {
  maintenance: MaintenanceWindow;
  onUpdate: () => void;
}

const MaintenanceLiveDashboard = ({ maintenance, onUpdate }: Props) => {
  const [now, setNow] = useState(new Date());
  const [actionLoading, setActionLoading] = useState(false);
  const [editingMessage, setEditingMessage] = useState(false);
  const [newMessage, setNewMessage] = useState(maintenance.message);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    setNewMessage(maintenance.message);
  }, [maintenance.message]);

  const startsAt = new Date(maintenance.starts_at);
  const endsAt = new Date(maintenance.ends_at);

  const elapsedMs = Math.max(0, now.getTime() - startsAt.getTime());
  const remainingMs = Math.max(0, endsAt.getTime() - now.getTime());

  const fmt = (ms: number) => {
    const totalMin = Math.floor(ms / 60000);
    const h = Math.floor(totalMin / 60);
    const m = totalMin % 60;
    if (h > 0) return `${h}h ${m.toString().padStart(2, "0")}min`;
    return `${m} min`;
  };

  const handleEndNow = async () => {
    if (!confirm("Encerrar a manutenção agora? O sistema voltará imediatamente para os usuários.")) {
      return;
    }
    setActionLoading(true);
    try {
      const token = getToken();
      const res = await fetch(
        `${API_BASE_URL}/api/admin/maintenance/${maintenance.id}/end`,
        {
          method: "PATCH",
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      const data = await res.json();
      if (res.ok) {
        toast.success("Manutenção encerrada. Sistema voltou ao normal.");
        onUpdate();
      } else {
        toast.error(data.msg || "Erro ao encerrar.");
      }
    } catch {
      toast.error("Erro de rede.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleExtend = async (extraMinutes: number) => {
    setActionLoading(true);
    try {
      const token = getToken();
      const res = await fetch(
        `${API_BASE_URL}/api/admin/maintenance/${maintenance.id}/extend`,
        {
          method: "PATCH",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ extra_minutes: extraMinutes }),
        }
      );
      const data = await res.json();
      if (res.ok) {
        toast.success(`Manutenção estendida por ${extraMinutes} minutos.`);
        onUpdate();
      } else {
        toast.error(data.msg || "Erro ao estender.");
      }
    } catch {
      toast.error("Erro de rede.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleSaveMessage = async () => {
    if (!newMessage.trim()) {
      toast.error("Mensagem não pode ser vazia.");
      return;
    }
    setActionLoading(true);
    try {
      const token = getToken();
      const res = await fetch(
        `${API_BASE_URL}/api/admin/maintenance/${maintenance.id}`,
        {
          method: "PATCH",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ message: newMessage.trim() }),
        }
      );
      const data = await res.json();
      if (res.ok) {
        toast.success("Mensagem atualizada.");
        setEditingMessage(false);
        onUpdate();
      } else {
        toast.error(data.msg || "Erro ao salvar.");
      }
    } catch {
      toast.error("Erro de rede.");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border-2 border-red-500/40 bg-red-500/5 p-5"
    >
      {/* Header com pulse */}
      <div className="flex items-start justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-10 h-10 rounded-xl bg-red-500/15 flex items-center justify-center">
              <Power className="w-5 h-5 text-red-500" />
            </div>
            <span className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-red-500 animate-pulse" />
          </div>
          <div>
            <h3 className="text-base font-bold text-red-600 dark:text-red-400">
              MANUTENÇÃO EM CURSO
            </h3>
            <p className="text-xs text-muted-foreground">
              Sistema bloqueado para usuários comuns
              {maintenance.is_emergency && " · ⚡ Emergencial"}
            </p>
          </div>
        </div>

        <button
          onClick={handleEndNow}
          disabled={actionLoading}
          className="bg-emerald-500 hover:bg-emerald-600 text-white px-4 py-2 rounded-md text-sm font-semibold flex items-center gap-2 transition disabled:opacity-60"
        >
          <CheckCircle2 className="w-4 h-4" />
          Encerrar agora
        </button>
      </div>

      {/* Tempos */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-background/60 rounded-lg p-3 text-center">
          <div className="text-xs text-muted-foreground mb-1">Decorrido</div>
          <div className="text-xl font-bold text-foreground">{fmt(elapsedMs)}</div>
        </div>
        <div className="bg-background/60 rounded-lg p-3 text-center">
          <div className="text-xs text-muted-foreground mb-1">Restante</div>
          <div className={`text-xl font-bold ${remainingMs <= 5 * 60000 ? "text-amber-500" : "text-foreground"}`}>
            {fmt(remainingMs)}
          </div>
        </div>
        <div className="bg-background/60 rounded-lg p-3 text-center">
          <div className="text-xs text-muted-foreground mb-1">Fim previsto</div>
          <div className="text-sm font-semibold text-foreground">
            {endsAt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
          </div>
        </div>
      </div>

      {/* Mensagem ativa */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">
            Mensagem aos usuários
          </span>
          {!editingMessage && (
            <button
              onClick={() => setEditingMessage(true)}
              className="text-xs text-primary hover:underline flex items-center gap-1"
            >
              <Edit2 className="w-3 h-3" />
              Editar
            </button>
          )}
        </div>

        {editingMessage ? (
          <div className="space-y-2">
            <textarea
              value={newMessage}
              onChange={(e) => setNewMessage(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 outline-none focus:border-primary resize-y"
            />
            <div className="flex gap-2">
              <button
                onClick={() => { setEditingMessage(false); setNewMessage(maintenance.message); }}
                disabled={actionLoading}
                className="px-3 py-1.5 text-xs rounded-md border border-border/50 hover:bg-muted/30 transition"
              >
                Cancelar
              </button>
              <button
                onClick={handleSaveMessage}
                disabled={actionLoading}
                className="gradient-primary text-primary-foreground px-3 py-1.5 text-xs font-semibold rounded-md flex items-center gap-1.5 hover:opacity-90 transition disabled:opacity-60"
              >
                {actionLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}
                Salvar
              </button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-foreground bg-background/60 rounded-md p-3 whitespace-pre-line">
            {maintenance.message}
          </p>
        )}
      </div>

      {/* Estender duração */}
      <div>
        <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium block mb-2">
          Estender duração
        </span>
        <div className="flex gap-2 flex-wrap">
          {[15, 30, 60, 120].map((m) => (
            <button
              key={m}
              onClick={() => handleExtend(m)}
              disabled={actionLoading}
              className="text-xs px-3 py-1.5 rounded-md border border-border/50 text-foreground hover:bg-amber-500/10 hover:border-amber-500/30 transition flex items-center gap-1 disabled:opacity-50"
            >
              <Plus className="w-3 h-3" />
              {m < 60 ? `${m}min` : `${m / 60}h`}
            </button>
          ))}
        </div>
      </div>
    </motion.div>
  );
};

export default MaintenanceLiveDashboard;
