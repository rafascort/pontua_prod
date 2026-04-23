// frontend/src/pages/MinhasIndicacoes.tsx
//
// Página /indicacoes — visão completa das indicações feitas pelo usuário.
// v2: inclui card para aplicar código retroativamente (se aplicável)

import { motion } from "framer-motion";
import {
  ArrowLeft, Loader2, Users, CheckCircle2, Clock,
} from "lucide-react";
import { Link } from "react-router-dom";
import AppHeader from "@/components/AppHeader";
import ReferralCard from "@/components/ReferralCard";
import ApplyReferralCode from "@/components/ApplyReferralCode";
import { useReferralHistory } from "@/hooks/useReferralStats";

const MinhasIndicacoes = () => {
  const { items, isLoading } = useReferralHistory();

  const formatDate = (iso: string | null) => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleDateString("pt-BR", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      });
    } catch {
      return "—";
    }
  };

  const planLabel: Record<string, string> = {
    basic: "Básico",
    standard: "Padrão",
    premium: "Premium",
  };

  return (
    <div className="min-h-screen gradient-bg">
      <AppHeader />

      <main className="container mx-auto max-w-4xl px-6 py-8">
        <Link
          to="/app"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition mb-6"
        >
          <ArrowLeft className="w-4 h-4" />
          Voltar
        </Link>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
              <Users className="w-5 h-5 text-primary" />
            </div>
            <h1 className="text-3xl font-bold text-foreground">
              Minhas Indicações
            </h1>
          </div>
          <p className="text-muted-foreground">
            Indique amigos e ganhe 10% por cada assinatura — até 40% por mês.
          </p>
        </motion.div>

        {/* Card principal de indicação */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="mb-4"
        >
          <ReferralCard variant="full" />
        </motion.div>

        {/* ── v2: Aplicar código retroativamente ─────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="mb-8"
        >
          <ApplyReferralCode />
        </motion.div>

        {/* Histórico */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <h2 className="text-lg font-semibold text-foreground mb-4">
            Histórico de indicações
          </h2>

          <div className="glass-card overflow-hidden">
            {isLoading ? (
              <div className="p-8 flex justify-center">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            ) : items.length === 0 ? (
              <div className="p-10 text-center">
                <Users className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
                <p className="text-sm text-muted-foreground">
                  Você ainda não indicou ninguém.
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Use o link de indicação acima para começar.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border/50 bg-muted/20">
                      <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground uppercase">
                        Email indicado
                      </th>
                      <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground uppercase">
                        Status
                      </th>
                      <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground uppercase">
                        Plano
                      </th>
                      <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground uppercase">
                        Data
                      </th>
                      <th className="text-right px-4 py-3 text-xs font-medium text-muted-foreground uppercase">
                        Desconto
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item) => (
                      <tr
                        key={item.id}
                        className="border-b border-border/30 last:border-0 hover:bg-muted/20"
                      >
                        <td className="px-4 py-3 text-foreground text-xs font-mono">
                          {item.referred_email_masked}
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge status={item.status} />
                        </td>
                        <td className="px-4 py-3 text-muted-foreground text-xs">
                          {item.plan ? (planLabel[item.plan] ?? item.plan) : "—"}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {formatDate(item.created_at)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          {item.status === "converted" ? (
                            <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                              +{item.discount_pct}%
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </motion.div>
      </main>
    </div>
  );
};

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { cls: string; label: string; icon: React.ReactNode }> = {
    converted: {
      cls: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
      label: "Convertido",
      icon: <CheckCircle2 className="w-3 h-3" />,
    },
    pending: {
      cls: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
      label: "Aguardando",
      icon: <Clock className="w-3 h-3" />,
    },
    expired: {
      cls: "bg-muted text-muted-foreground",
      label: "Expirado",
      icon: null,
    },
  };
  const c = config[status] ?? config.expired;
  return (
    <span
      className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded ${c.cls}`}
    >
      {c.icon}
      {c.label}
    </span>
  );
}

export default MinhasIndicacoes;
