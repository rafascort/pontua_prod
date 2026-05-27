// frontend/src/components/PlanManagerModal.tsx
import { useEffect, useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Check, ArrowUp, ArrowDown, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const PLAN_RANK: Record<string, number> = { basic: 1, standard: 2, premium: 3 };

const PLANS = [
  {
    id: "basic", name: "Básico", price: "R$ 179,90",
    pages: "200 páginas/mês", extra: "R$ 1,00 por página extra",
    priceId: import.meta.env.VITE_STRIPE_PRICE_ID_BASICO as string,
  },
  {
    id: "standard", name: "Padrão", price: "R$ 349,90",
    pages: "500 páginas/mês", extra: "R$ 0,85 por página extra",
    priceId: import.meta.env.VITE_STRIPE_PRICE_ID_PADRAO as string, highlight: true,
  },
  {
    id: "premium", name: "Premium", price: "R$ 824,90",
    pages: "1.500 páginas/mês", extra: "R$ 0,70 por página extra",
    priceId: import.meta.env.VITE_STRIPE_PRICE_ID_PREMIUM as string,
  },
];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentPlan: string;            // "basic" | "standard" | "premium"
  scheduledPlan?: string | null;  // plano agendado (downgrade pendente)
  onChanged: () => void;          // callback p/ recarregar status após troca
}

export default function PlanManagerModal({
  open, onOpenChange, currentPlan, scheduledPlan, onChanged,
}: Props) {
  const { refreshUser } = useAuth();
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [confirmDowngrade, setConfirmDowngrade] = useState<typeof PLANS[0] | null>(null);

  const curRank = PLAN_RANK[currentPlan] ?? 0;

  const doChange = async (priceId: string, planId: string) => {
    setLoadingId(planId);
    try {
      const res = await api.changePlan(priceId);
      if (res.type === "upgrade") {
        toast.success("Upgrade aplicado! A diferença proporcional entra na próxima fatura.");
      } else {
        toast.success("Downgrade agendado para o fim do ciclo atual.");
      }
      await refreshUser();
      onChanged();
      onOpenChange(false);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Erro ao trocar de plano.");
    } finally {
      setLoadingId(null);
      setConfirmDowngrade(null);
    }
  };

  const handleClick = (p: typeof PLANS[0]) => {
    const newRank = PLAN_RANK[p.id];
    if (p.id === currentPlan) return;
    if (newRank < curRank) {
      setConfirmDowngrade(p); // downgrade pede confirmação
    } else {
      doChange(p.priceId, p.id); // upgrade direto
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-3xl bg-card border-border/50">
          <DialogHeader>
            <DialogTitle>Gerenciar plano</DialogTitle>
            <DialogDescription>
              Upgrades são aplicados na hora (cobrança proporcional na próxima fatura).
              Downgrades entram em vigor no fim do ciclo atual.
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-2">
            {PLANS.map((p) => {
              const isCurrent   = p.id === currentPlan;
              const isScheduled = p.id === scheduledPlan;
              const newRank     = PLAN_RANK[p.id];
              const isUpgrade   = newRank > curRank;
              const busy        = loadingId === p.id;

              return (
                <div
                  key={p.id}
                  className={`glass-card p-5 flex flex-col relative ${
                    p.highlight ? "border-primary/50" : ""
                  } ${isCurrent ? "ring-2 ring-primary" : ""}`}
                >
                  {isCurrent && (
                    <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 gradient-primary rounded-full text-xs font-bold text-primary-foreground whitespace-nowrap">
                      Plano atual
                    </div>
                  )}
                  {isScheduled && !isCurrent && (
                    <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-warning/20 border border-warning/30 rounded-full text-xs font-medium text-warning whitespace-nowrap">
                      Agendado
                    </div>
                  )}

                  <h4 className="text-base font-bold text-foreground mb-1">{p.name}</h4>
                  <div className="text-2xl font-extrabold text-foreground mb-3">{p.price}</div>
                  <ul className="flex-1 space-y-2 mb-5 text-sm text-muted-foreground">
                    <li className="flex items-center gap-2"><span className="text-success">✓</span> {p.pages}</li>
                    <li className="flex items-center gap-2"><span className="text-success">✓</span> {p.extra}</li>
                  </ul>

                  <button
                    disabled={isCurrent || busy}
                    onClick={() => handleClick(p)}
                    className={`w-full py-2.5 rounded-lg text-sm font-semibold transition-all flex items-center justify-center gap-2 ${
                      isCurrent
                        ? "border border-border/30 text-muted-foreground cursor-not-allowed opacity-50"
                        : isUpgrade
                          ? "gradient-primary text-primary-foreground hover:shadow-lg hover:shadow-primary/25"
                          : "border border-border hover:bg-secondary/60 text-foreground"
                    }`}
                  >
                    {busy && <Loader2 className="w-4 h-4 animate-spin" />}
                    {isCurrent ? "Plano atual"
                      : isUpgrade ? (<><ArrowUp className="w-4 h-4" /> Fazer upgrade</>)
                      : (<><ArrowDown className="w-4 h-4" /> Mudar para este</>)}
                  </button>
                </div>
              );
            })}
          </div>
        </DialogContent>
      </Dialog>

      {/* Confirmação de downgrade */}
      <AlertDialog open={!!confirmDowngrade} onOpenChange={(o) => !o && setConfirmDowngrade(null)}>
        <AlertDialogContent className="bg-card border-border/50">
          <AlertDialogHeader>
            <AlertDialogTitle>Confirmar mudança para {confirmDowngrade?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              Você continua no seu plano atual até o fim do ciclo. Na próxima renovação,
              a assinatura muda para o plano {confirmDowngrade?.name} ({confirmDowngrade?.price}).
              Você pode cancelar essa mudança a qualquer momento antes da renovação.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Voltar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => confirmDowngrade && doChange(confirmDowngrade.priceId, confirmDowngrade.id)}
            >
              Confirmar mudança
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
