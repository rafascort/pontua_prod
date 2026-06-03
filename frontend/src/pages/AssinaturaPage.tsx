// frontend/src/pages/AssinaturaPage.tsx
//
// Página dedicada de gerenciamento de assinatura (substitui o PlanManagerModal).
// Estados pessoais cobertos:
//   • free / inactive  → assina via Stripe Checkout (createCheckoutSession)
//   • basic/standard/premium → troca de plano via /api/change-plan
//        - UPGRADE: o cliente escolhe — "agora" (proração, com prévia de valor real)
//                   ou "no fim do ciclo" (agendado, sem custo hoje)
//        - DOWNGRADE: agendado p/ fim do ciclo (badge "Agendado")
//   • past_due → bloqueia troca e direciona p/ atualizar pagamento no portal
//   • org users → redirecionados (assinatura da empresa fica em /empresa)
//
// Correções desta versão:
//   1. F5: após trocar, o estado é atualizado de forma OTIMISTA (não depende
//      da releitura imediata do Stripe, que sofria corrida de tempo).
//   2. Prévia de valor real do upgrade imediato (Invoice preview do Stripe)
//      mostrada no diálogo antes de confirmar.

import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowLeft, ArrowUp, ArrowDown, Check, Loader2,
  CreditCard, Receipt, AlertTriangle, Sparkles,
} from "lucide-react";
import {
  AlertDialog, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import AppHeader from "@/components/AppHeader";
import { useUserPlan } from "@/hooks/useUserPlan";
import { getPlanDisplayName } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { toast } from "sonner";

const ACTIVE_PLANS = ["basic", "standard", "premium"];
const PLAN_RANK: Record<string, number> = { basic: 1, standard: 2, premium: 3 };

interface PlanDef {
  id: string;
  name: string;
  price: string;
  pages: string;
  extra: string;
  priceId: string;
  highlight?: boolean;
}

const PLANS: PlanDef[] = [
  {
    id: "basic", name: "Básico", price: "R$ 179,90",
    pages: "200 páginas/mês", extra: "R$ 1,00 por página extra",
    priceId: import.meta.env.VITE_STRIPE_PRICE_ID_BASICO as string,
  },
  {
    id: "standard", name: "Padrão", price: "R$ 349,90",
    pages: "500 páginas/mês", extra: "R$ 0,85 por página extra", highlight: true,
    priceId: import.meta.env.VITE_STRIPE_PRICE_ID_PADRAO as string,
  },
  {
    id: "premium", name: "Premium", price: "R$ 824,90",
    pages: "1.500 páginas/mês", extra: "R$ 0,70 por página extra",
    priceId: import.meta.env.VITE_STRIPE_PRICE_ID_PREMIUM as string,
  },
];

function jwtClaims(): Record<string, unknown> {
  try {
    const token = localStorage.getItem("access_token");
    if (!token) return {};
    return JSON.parse(atob(token.split(".")[1]));
  } catch {
    return {};
  }
}

const fmtBRL = (cents: number) =>
  (cents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

type ConfirmKind = "subscribe" | "upgrade" | "downgrade";
interface ConfirmState {
  plan: PlanDef;
  kind: ConfirmKind;
}

export default function AssinaturaPage() {
  const { plan, isLoading: planLoading, refreshUser } = useUserPlan();
  const navigate = useNavigate();

  const orgId = jwtClaims().organization_id;

  const [subStatus, setSubStatus] = useState<{
    current_plan: string;
    scheduled_change: { plan: string; effective_date: number } | null;
  } | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [confirm, setConfirm] = useState<ConfirmState | null>(null);
  const [preview, setPreview] = useState<{ loading: boolean; amount: number | null }>({
    loading: false, amount: null,
  });

  const isPaidPlan = ACTIVE_PLANS.includes(plan.planStatus);
  const isFree     = plan.planStatus === "free";
  const isPastDue  = plan.planStatus === "past_due";

  // Usuário de empresa não gerencia assinatura pessoal aqui.
  useEffect(() => {
    if (orgId) navigate("/app", { replace: true });
  }, [orgId, navigate]);

  const loadSubStatus = useCallback(() => {
    if (!ACTIVE_PLANS.includes(plan.planStatus)) {
      setSubStatus({ current_plan: plan.planStatus, scheduled_change: null });
      return;
    }
    api.getSubscriptionStatus()
      .then(setSubStatus)
      .catch(() =>
        setSubStatus({ current_plan: plan.planStatus, scheduled_change: null })
      );
  }, [plan.planStatus]);

  useEffect(() => { loadSubStatus(); }, [loadSubStatus]);

  const currentPlan   = subStatus?.current_plan ?? plan.planStatus;
  const scheduledPlan = subStatus?.scheduled_change?.plan ?? null;
  const curRank       = PLAN_RANK[currentPlan] ?? 0;

  // ── Uso no ciclo ──────────────────────────────────────────────────────
  const usedInPlan = Math.max(0, Math.min(plan.pageCount - plan.extraPages, plan.pageLimit));
  const fillPct = plan.pageLimit > 0
    ? Math.min(100, Math.round((usedInPlan / plan.pageLimit) * 100))
    : 0;

  // ── Prévia de valor (upgrade imediato) ────────────────────────────────
  const fetchPreview = async (priceId: string) => {
    setPreview({ loading: true, amount: null });
    try {
      const r = await api.previewChangePlan(priceId);
      setPreview({ loading: false, amount: r.amount_due });
    } catch {
      setPreview({ loading: false, amount: null });
    }
  };

  // ── Ações ─────────────────────────────────────────────────────────────
  const askConfirm = (p: PlanDef) => {
    if (p.id === currentPlan) return;
    if (isPastDue) {
      toast.info("Regularize o pagamento pendente antes de trocar de plano.");
      return;
    }
    if (!isPaidPlan) {
      setConfirm({ plan: p, kind: "subscribe" });
      return;
    }
    const kind: ConfirmKind = PLAN_RANK[p.id] > curRank ? "upgrade" : "downgrade";
    setConfirm({ plan: p, kind });
    if (kind === "upgrade") fetchPreview(p.priceId);
  };

  const closeDialog = () => {
    setConfirm(null);
    setPreview({ loading: false, amount: null });
  };

  // mode só importa p/ upgrade: "now" (proração) ou "period_end" (agendado)
  const executeChange = async (mode: "now" | "period_end") => {
    if (!confirm) return;
    const { plan: p, kind } = confirm;
    setLoadingId(p.id);
    try {
      if (kind === "subscribe") {
        const { url } = await api.createCheckoutSession(p.priceId);
        if (url) { window.location.href = url; return; }
        toast.error("Não foi possível abrir o checkout.");
        return;
      }

      const when: "now" | "period_end" = kind === "downgrade" ? "period_end" : mode;
      const res = await api.changePlan(p.priceId, when);

      toast.success(
        res.effective === "now"
          ? "Upgrade aplicado! A diferença proporcional entra na próxima fatura."
          : "Mudança agendada para o fim do ciclo atual."
      );

      // Atualização OTIMISTA — corrige o "só aparece após F5".
      if (res.effective === "now") {
        setSubStatus({ current_plan: res.plan, scheduled_change: null });
      } else {
        setSubStatus((prev) => ({
          current_plan: prev?.current_plan ?? currentPlan,
          scheduled_change: {
            plan: res.plan,
            effective_date: prev?.scheduled_change?.effective_date ?? 0,
          },
        }));
      }

      await refreshUser();
      // Reconcilia com o Stripe em seguida (pega data real do agendamento etc.)
      setTimeout(loadSubStatus, 1500);
    } catch (err: unknown) {
      toast.error(
        err instanceof Error ? err.message : "Erro ao processar a mudança de plano."
      );
    } finally {
      setLoadingId(null);
      closeDialog();
    }
  };

  const openPortal = async () => {
    setPortalLoading(true);
    try {
      const token = localStorage.getItem("access_token");
      const r = await fetch("/api/create-portal-session", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      });
      if (!r.ok) { toast.error("Erro ao abrir o portal de pagamento."); return; }
      const d = await r.json();
      if (d.url) window.location.href = d.url;
      else toast.error("URL do portal não retornada.");
    } catch {
      toast.error("Erro de conexão ao abrir o portal.");
    } finally {
      setPortalLoading(false);
    }
  };

  // ── Loading inicial ────────────────────────────────────────────────────
  if (planLoading) {
    return (
      <>
        <AppHeader />
        <div className="container mx-auto px-4 py-10 max-w-5xl">
          <div className="h-7 w-56 bg-secondary/60 rounded animate-pulse mb-6" />
          <div className="h-32 bg-secondary/40 rounded-2xl animate-pulse mb-6" />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="h-56 bg-secondary/40 rounded-2xl animate-pulse" />
            <div className="h-56 bg-secondary/40 rounded-2xl animate-pulse" />
            <div className="h-56 bg-secondary/40 rounded-2xl animate-pulse" />
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <AppHeader />

      <div className="container mx-auto px-4 py-8 max-w-5xl">
        {/* Voltar + título */}
        <Link
          to="/app"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-4"
        >
          <ArrowLeft className="w-4 h-4" /> Voltar
        </Link>
        <h1 className="text-2xl font-bold text-foreground mb-1">Gerenciar assinatura</h1>
        <p className="text-sm text-muted-foreground mb-6">
          Veja seu plano, troque quando quiser e gerencie pagamento e faturas.
        </p>

        {/* Alerta de pagamento pendente */}
        {isPastDue && (
          <div className="mb-6 flex items-start gap-3 p-4 rounded-xl bg-destructive/10 border border-destructive/30">
            <AlertTriangle className="w-5 h-5 text-destructive shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-foreground">Pagamento pendente</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Seu último pagamento falhou. Atualize a forma de pagamento para reativar
                a assinatura. A troca de plano fica disponível após a regularização.
              </p>
              <button
                onClick={openPortal}
                disabled={portalLoading}
                className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-lg gradient-primary text-primary-foreground text-sm font-semibold disabled:opacity-50"
              >
                {portalLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <CreditCard className="w-4 h-4" />}
                Atualizar forma de pagamento
              </button>
            </div>
          </div>
        )}

        {/* Status atual */}
        <div className="glass-card p-5 mb-6">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
                Plano atual
              </p>
              <p className="text-xl font-bold text-foreground mt-0.5">{plan.planName}</p>
            </div>
            {scheduledPlan && (
              <span className="px-3 py-1 rounded-full text-xs font-medium bg-amber-500/15 text-amber-400 border border-amber-500/30">
                Mudança agendada → {getPlanDisplayName(scheduledPlan)}
              </span>
            )}
          </div>

          {isPaidPlan && (
            <div className="mt-4">
              <div className="flex items-center justify-between text-sm mb-1.5">
                <span className="text-muted-foreground">Páginas usadas no ciclo</span>
                <span className="text-foreground font-medium">
                  {usedInPlan} / {plan.pageLimit}
                  {plan.extraPages > 0 && (
                    <span className="text-amber-400">
                      {" "}+{plan.extraPages} extra{plan.extraPages > 1 ? "s" : ""}
                    </span>
                  )}
                </span>
              </div>
              <div className="h-2 rounded-full bg-secondary/60 overflow-hidden">
                <div
                  className={`h-full ${plan.extraPages > 0 ? "bg-amber-400/80" : "bg-primary"}`}
                  style={{ width: `${fillPct}%` }}
                />
              </div>
              {plan.extraPages > 0 && (
                <p className="text-[11px] text-muted-foreground mt-2">
                  Páginas extras são cobradas automaticamente na próxima fatura.
                </p>
              )}
            </div>
          )}

          {isFree && (
            <div className="mt-4">
              <div className="flex items-center justify-between text-sm mb-1.5">
                <span className="text-muted-foreground">Páginas do teste grátis</span>
                <span className="text-foreground font-medium">
                  {plan.pageCount} / {plan.pageLimit} usadas
                </span>
              </div>
              <div className="h-2 rounded-full bg-secondary/60 overflow-hidden">
                <div
                  className={`h-full ${plan.pageBalance <= 0 ? "bg-destructive/70" : "bg-primary"}`}
                  style={{ width: `${fillPct}%` }}
                />
              </div>
              <p className="text-[11px] text-muted-foreground mt-2">
                {plan.pageBalance > 0
                  ? `${plan.pageBalance} páginas restantes no teste grátis.`
                  : "Seu teste grátis acabou. Assine um plano para continuar."}
              </p>
            </div>
          )}
        </div>

        {/* Planos */}
        <h2 className="text-sm font-semibold text-foreground mb-3">
          {isPaidPlan ? "Trocar de plano" : "Escolha um plano"}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {PLANS.map((p) => {
            const isCurrent   = p.id === currentPlan;
            const isScheduled = p.id === scheduledPlan;
            const isUpgrade   = PLAN_RANK[p.id] > curRank;
            const busy        = loadingId === p.id;
            const disabled    = isCurrent || busy || isPastDue;

            const label =
              isCurrent      ? "Plano atual"
              : !isPaidPlan  ? "Assinar"
              : isUpgrade    ? "Fazer upgrade"
              :                "Mudar para este";

            const primaryStyle = (isUpgrade || !isPaidPlan) && !isCurrent && !isPastDue;

            return (
              <div
                key={p.id}
                className={`glass-card p-5 flex flex-col relative ${p.highlight ? "border-primary/50" : ""} ${isCurrent ? "ring-2 ring-primary" : ""}`}
              >
                {isCurrent && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 gradient-primary rounded-full text-xs font-bold text-primary-foreground whitespace-nowrap">
                    Plano atual
                  </div>
                )}
                {isScheduled && !isCurrent && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-amber-500/20 border border-amber-500/30 rounded-full text-xs font-medium text-amber-400 whitespace-nowrap">
                    Agendado
                  </div>
                )}
                {p.highlight && !isCurrent && !isScheduled && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-primary/15 border border-primary/30 rounded-full text-[10px] font-semibold text-primary whitespace-nowrap flex items-center gap-1">
                    <Sparkles className="w-3 h-3" /> Mais popular
                  </div>
                )}

                <h3 className="text-base font-bold text-foreground mb-1 mt-1">{p.name}</h3>
                <div className="text-2xl font-extrabold text-foreground mb-3">
                  {p.price}
                  <span className="text-sm font-normal text-muted-foreground">/mês</span>
                </div>
                <ul className="flex-1 space-y-2 mb-5 text-sm text-muted-foreground">
                  <li className="flex items-center gap-2">
                    <Check className="w-4 h-4 text-success shrink-0" /> {p.pages}
                  </li>
                  <li className="flex items-center gap-2">
                    <Check className="w-4 h-4 text-success shrink-0" /> {p.extra}
                  </li>
                </ul>

                <button
                  disabled={disabled}
                  onClick={() => askConfirm(p)}
                  className={`w-full py-2.5 rounded-lg text-sm font-semibold transition-all flex items-center justify-center gap-2 ${
                    disabled
                      ? "border border-border/30 text-muted-foreground cursor-not-allowed opacity-50"
                      : primaryStyle
                        ? "gradient-primary text-primary-foreground hover:shadow-lg hover:shadow-primary/25"
                        : "border border-border hover:bg-secondary/60 text-foreground"
                  }`}
                >
                  {busy && <Loader2 className="w-4 h-4 animate-spin" />}
                  {!busy && isPaidPlan && !isCurrent &&
                    (isUpgrade ? <ArrowUp className="w-4 h-4" /> : <ArrowDown className="w-4 h-4" />)}
                  {label}
                </button>
              </div>
            );
          })}
        </div>

        {/* Pagamento e faturas — só quem tem assinatura no Stripe */}
        {(isPaidPlan || isPastDue) && (
          <div className="glass-card p-5 mt-6 flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-secondary/60 flex items-center justify-center shrink-0">
                <Receipt className="w-5 h-5 text-muted-foreground" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">Forma de pagamento e faturas</p>
                <p className="text-xs text-muted-foreground">
                  Atualize o cartão, baixe faturas ou cancele a assinatura no portal seguro do Stripe.
                </p>
              </div>
            </div>
            <button
              onClick={openPortal}
              disabled={portalLoading}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-border hover:bg-secondary/60 text-foreground text-sm font-medium disabled:opacity-50"
            >
              {portalLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <CreditCard className="w-4 h-4" />}
              Abrir portal
            </button>
          </div>
        )}
      </div>

      {/* Confirmação */}
      <AlertDialog open={!!confirm} onOpenChange={(o) => !o && closeDialog()}>
        <AlertDialogContent className="bg-card border-border/50">

          {confirm?.kind === "subscribe" && (
            <>
              <AlertDialogHeader>
                <AlertDialogTitle>Assinar plano {confirm.plan.name}?</AlertDialogTitle>
                <AlertDialogDescription>
                  Você será levado ao checkout seguro do Stripe para assinar o plano{" "}
                  {confirm.plan.name} ({confirm.plan.price}/mês).
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Voltar</AlertDialogCancel>
                <button
                  onClick={() => executeChange("now")}
                  disabled={loadingId !== null}
                  className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg gradient-primary text-primary-foreground text-sm font-semibold disabled:opacity-50"
                >
                  {loadingId !== null && <Loader2 className="w-4 h-4 animate-spin" />}
                  Ir para o checkout
                </button>
              </AlertDialogFooter>
            </>
          )}

          {confirm?.kind === "downgrade" && (
            <>
              <AlertDialogHeader>
                <AlertDialogTitle>Mudar para {confirm.plan.name}?</AlertDialogTitle>
                <AlertDialogDescription>
                  Você continua no plano atual até o fim do ciclo. Na próxima renovação a
                  assinatura muda para {confirm.plan.name} ({confirm.plan.price}). Você pode
                  cancelar essa mudança antes da renovação.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Voltar</AlertDialogCancel>
                <button
                  onClick={() => executeChange("period_end")}
                  disabled={loadingId !== null}
                  className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg gradient-primary text-primary-foreground text-sm font-semibold disabled:opacity-50"
                >
                  {loadingId !== null && <Loader2 className="w-4 h-4 animate-spin" />}
                  Agendar mudança
                </button>
              </AlertDialogFooter>
            </>
          )}

          {confirm?.kind === "upgrade" && (
            <>
              <AlertDialogHeader>
                <AlertDialogTitle>Fazer upgrade para {confirm.plan.name}?</AlertDialogTitle>
                <AlertDialogDescription>
                  Escolha quando o upgrade entra em vigor. Você passa a ter {confirm.plan.pages}.
                </AlertDialogDescription>
              </AlertDialogHeader>

              <div className="space-y-3 mt-1">
                {/* Opção: agora (proração) */}
                <div>
                  <button
                    onClick={() => executeChange("now")}
                    disabled={loadingId !== null}
                    className="w-full p-3 rounded-lg gradient-primary text-primary-foreground text-sm font-semibold text-left flex items-center justify-between gap-3 disabled:opacity-50"
                  >
                    <span className="flex items-center gap-2">
                      {loadingId !== null && <Loader2 className="w-4 h-4 animate-spin" />}
                      Fazer upgrade agora
                    </span>
                    <span className="text-xs opacity-90 whitespace-nowrap">
                      {preview.loading
                        ? "calculando…"
                        : preview.amount != null
                          ? `${fmtBRL(preview.amount)} agora`
                          : "valor proporcional"}
                    </span>
                  </button>
                  <p className="text-[11px] text-muted-foreground px-1 mt-1">
                    Cobrança proporcional aos dias restantes do ciclo. Você usa as páginas
                    do novo plano imediatamente.
                  </p>
                </div>

                {/* Opção: fim do ciclo (agendado) */}
                <div>
                  <button
                    onClick={() => executeChange("period_end")}
                    disabled={loadingId !== null}
                    className="w-full p-3 rounded-lg border border-border hover:bg-secondary/60 text-foreground text-sm font-semibold text-left flex items-center justify-between gap-3 disabled:opacity-50"
                  >
                    <span>Agendar para o próximo ciclo</span>
                    <span className="text-xs text-muted-foreground whitespace-nowrap">sem custo hoje</span>
                  </button>
                  <p className="text-[11px] text-muted-foreground px-1 mt-1">
                    Sem cobrança agora. O novo plano passa a valer a partir da próxima renovação.
                  </p>
                </div>
              </div>

              <AlertDialogFooter className="mt-2">
                <AlertDialogCancel>Voltar</AlertDialogCancel>
              </AlertDialogFooter>
            </>
          )}

        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
