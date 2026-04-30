// frontend/src/components/admin/MaintenanceEmergencyModal.tsx
//
// Modal de manutenção emergencial — ativa imediatamente.
// Confirmação de 1 clique, mas com aviso claro do impacto.

import { useState } from "react";
import { X, Loader2, Zap, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function getToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("jwt_token");
}

interface Props {
  onClose: () => void;
  onSaved: () => void;
}

const MaintenanceEmergencyModal = ({ onClose, onSaved }: Props) => {
  const [duration, setDuration] = useState(60); // minutos
  const [message, setMessage] = useState(
    "Sistema temporariamente fora do ar para correção urgente. Voltamos em breve."
  );
  const [confirming, setConfirming] = useState(false);

  const handleConfirm = async () => {
    if (!message.trim()) {
      toast.error("Mensagem não pode ser vazia.");
      return;
    }

    setConfirming(true);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE_URL}/api/admin/maintenance/emergency`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          duration_minutes: duration,
          message: message.trim(),
        }),
      });
      const data = await res.json();
      if (res.ok) {
        toast.success("Manutenção emergencial ativada!", { duration: 4000 });
        onSaved();
      } else {
        toast.error(data.msg || "Erro ao ativar.");
      }
    } catch {
      toast.error("Erro de rede.");
    } finally {
      setConfirming(false);
    }
  };

  const formatEnd = () => {
    const end = new Date(Date.now() + duration * 60 * 1000);
    return end.toLocaleString("pt-BR", {
      day: "2-digit", month: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  };

  return (
    <div className="fixed inset-0 z-[90] bg-background/85 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-md rounded-2xl bg-card border border-red-500/30 shadow-2xl overflow-hidden">

        {/* Header vermelho */}
        <div className="bg-red-500/10 border-b border-red-500/30 px-6 py-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-red-600 dark:text-red-400 flex items-center gap-2">
            <Zap className="w-5 h-5" />
            Manutenção emergencial
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-red-500/20 text-red-600 dark:text-red-400"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-5">

          {/* Aviso importante */}
          <div className="flex gap-3 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30">
            <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
            <div className="text-sm text-foreground">
              <strong className="text-amber-600 dark:text-amber-400">Atenção:</strong>
              {" "}Esta ação BLOQUEIA o sistema imediatamente para todos os usuários comuns.
              Você poderá encerrar a qualquer momento ou estender se precisar.
            </div>
          </div>

          {/* Duração */}
          <div>
            <label className="text-sm font-medium text-foreground mb-2 block">
              Duração estimada
            </label>
            <div className="grid grid-cols-4 gap-2 mb-2">
              {[15, 30, 60, 120].map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setDuration(m)}
                  className={`text-xs py-2 rounded-md border transition ${
                    duration === m
                      ? "border-red-500 bg-red-500/10 text-red-600 dark:text-red-400"
                      : "border-border/50 text-muted-foreground hover:bg-muted/30"
                  }`}
                >
                  {m < 60 ? `${m}min` : `${m / 60}h`}
                </button>
              ))}
            </div>
            <input
              type="number"
              value={duration}
              onChange={(e) => setDuration(Math.max(5, Math.min(1440, parseInt(e.target.value) || 60)))}
              min={5}
              max={1440}
              className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 outline-none focus:border-red-500"
            />
            <div className="text-[11px] text-muted-foreground mt-1">
              Fim previsto: <strong className="text-foreground">{formatEnd()}</strong>
            </div>
          </div>

          {/* Mensagem */}
          <div>
            <label className="text-sm font-medium text-foreground mb-2 block">
              Mensagem na tela de bloqueio
            </label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 outline-none focus:border-red-500 resize-y"
            />
          </div>

          {/* Botões */}
          <div className="flex gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={confirming}
              className="flex-1 px-4 py-3 text-sm rounded-md border border-border/50 hover:bg-muted/30 transition disabled:opacity-50"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={confirming}
              className="flex-1 bg-red-500 hover:bg-red-600 text-white px-4 py-3 text-sm font-semibold rounded-md flex items-center justify-center gap-2 transition disabled:opacity-60"
            >
              {confirming ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Ativando...</>
              ) : (
                <><Zap className="w-4 h-4" /> Ativar AGORA</>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MaintenanceEmergencyModal;
