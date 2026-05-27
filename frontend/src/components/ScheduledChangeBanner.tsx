// frontend/src/components/ScheduledChangeBanner.tsx
import { useState } from "react";
import { CalendarClock, X, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const PLAN_LABEL: Record<string, string> = {
  basic: "Básico", standard: "Padrão", premium: "Premium",
};

interface Props {
  scheduledPlan: string;       // plano alvo do downgrade
  effectiveDate: number;       // unix timestamp (segundos)
  onCancelled: () => void;     // recarrega o status após cancelar
}

export default function ScheduledChangeBanner({ scheduledPlan, effectiveDate, onCancelled }: Props) {
  const [loading, setLoading] = useState(false);

  const dateStr = new Date(effectiveDate * 1000).toLocaleDateString("pt-BR", {
    day: "2-digit", month: "long", year: "numeric",
  });

  const handleCancel = async () => {
    setLoading(true);
    try {
      const res = await api.cancelScheduledChange();
      toast.success(res.msg || "Mudança cancelada.");
      onCancelled();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Erro ao cancelar.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-warning/10 border-b border-warning/30">
      <div className="container mx-auto flex items-center justify-between gap-3 px-4 py-2.5">
        <div className="flex items-center gap-2.5 text-sm text-foreground">
          <CalendarClock className="w-4 h-4 text-warning shrink-0" />
          <span>
            Seu plano muda para{" "}
            <strong className="text-warning">{PLAN_LABEL[scheduledPlan] ?? scheduledPlan}</strong>{" "}
            em <strong>{dateStr}</strong>. Até lá você mantém o plano atual.
          </span>
        </div>
        <button
          onClick={handleCancel}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border/50 text-xs font-medium text-foreground hover:bg-secondary/60 transition-all shrink-0 disabled:opacity-50"
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <X className="w-3.5 h-3.5" />}
          Manter plano atual
        </button>
      </div>
    </div>
  );
}
