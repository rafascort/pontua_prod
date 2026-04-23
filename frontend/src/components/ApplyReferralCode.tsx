// frontend/src/components/ApplyReferralCode.tsx
//
// Card para aplicar código de indicação retroativamente.
// Aparece em /indicacoes quando o usuário NÃO é assinante pago.
// Permite também trocar o código enquanto ele for válido.

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Gift, CheckCircle2, AlertCircle, Loader2, Pencil,
} from "lucide-react";
import { toast } from "sonner";
import {
  applyReferralCode,
  useReferralStats,
} from "@/hooks/useReferralStats";

const ApplyReferralCode = () => {
  const { stats, isLoading: statsLoading, refetch } = useReferralStats();

  const [code, setCode] = useState("");
  const [editing, setEditing] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Não mostra nada enquanto carrega
  if (statsLoading || !stats) {
    return null;
  }

  // Não pode mais aplicar código — usuário já é assinante pago
  if (!stats.can_change_referrer && !stats.referred_by_code) {
    return null;
  }

  const hasReferrer = !!stats.referred_by_code;
  const isLocked = !stats.can_change_referrer; // assinante pago trava

  const handleApply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!code.trim() || code.trim().length < 3) {
      toast.error("Informe um código válido.");
      return;
    }

    setSubmitting(true);
    const result = await applyReferralCode(code);
    setSubmitting(false);

    if (result.ok) {
      toast.success(result.msg);
      setCode("");
      setEditing(false);
      refetch();
    } else {
      toast.error(result.msg);
    }
  };

  // ── Estado 1: já tem indicador aplicado (não está editando) ──
  if (hasReferrer && !editing) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4"
      >
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-500/15 flex items-center justify-center shrink-0">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-foreground mb-0.5">
              Você foi indicado por {stats.referred_by_email_masked}
            </p>
            <p className="text-xs text-muted-foreground">
              {isLocked
                ? "O desconto foi aplicado na sua assinatura."
                : "O desconto será aplicado automaticamente na sua primeira assinatura paga."}
            </p>
          </div>
          {!isLocked && (
            <button
              onClick={() => setEditing(true)}
              className="shrink-0 inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors px-2 py-1 rounded"
            >
              <Pencil className="w-3.5 h-3.5" />
              Trocar
            </button>
          )}
        </div>
      </motion.div>
    );
  }

  // ── Estado 2: formulário de aplicação / troca ──
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-border/50 bg-muted/20 p-4"
    >
      <div className="flex items-start gap-3 mb-3">
        <div className="w-10 h-10 rounded-lg bg-indigo-500/10 flex items-center justify-center shrink-0">
          <Gift className="w-5 h-5 text-indigo-500 dark:text-indigo-400" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-semibold text-foreground mb-0.5">
            {editing ? "Trocar código de indicação" : "Alguém te indicou?"}
          </p>
          <p className="text-xs text-muted-foreground">
            {editing
              ? "Digite o novo código abaixo. O anterior será substituído."
              : "Insira o código de quem te indicou e ganhe desconto na sua primeira assinatura."}
          </p>
        </div>
      </div>

      <form onSubmit={handleApply} className="flex gap-2">
        <input
          type="text"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="EX: ABC12345"
          maxLength={20}
          disabled={submitting}
          autoComplete="off"
          className="flex-1 px-3 py-2 text-sm rounded-md bg-background border border-border/50 focus:border-primary outline-none font-mono uppercase placeholder:font-sans placeholder:normal-case disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={submitting || !code.trim()}
          className="gradient-primary text-primary-foreground px-4 py-2 rounded-md text-sm font-semibold flex items-center gap-2 hover:opacity-90 transition disabled:opacity-50"
        >
          {submitting ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : editing ? (
            "Trocar"
          ) : (
            "Aplicar"
          )}
        </button>

        {editing && (
          <button
            type="button"
            onClick={() => {
              setEditing(false);
              setCode("");
            }}
            disabled={submitting}
            className="px-3 py-2 rounded-md text-sm text-muted-foreground hover:text-foreground transition disabled:opacity-50"
          >
            Cancelar
          </button>
        )}
      </form>

      <div className="mt-2 flex items-start gap-1.5 text-[11px] text-muted-foreground">
        <AlertCircle className="w-3 h-3 shrink-0 mt-0.5" />
        <span>
          Você pode aplicar ou trocar o código enquanto ainda não tiver uma assinatura paga ativa.
        </span>
      </div>
    </motion.div>
  );
};

export default ApplyReferralCode;
