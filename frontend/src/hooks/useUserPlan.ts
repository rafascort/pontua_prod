// frontend/src/hooks/useUserPlan.ts
import { useAuth, getPlanDisplayName, getPlanLimit, getPageBalance } from "@/contexts/AuthContext";

export interface UserPlan {
  planName: string;
  pageBalance: number;
  pageLimit: number;
  extraPages: number;
  email: string;
  role: "user" | "admin";
  pageCount: number;
  planStatus: string;
  stripeCustomerId: string | null;
}

const ACTIVE_PLANS = ["basic", "standard", "premium"];

export function useUserPlan() {
  const { user, isLoading, refreshUser } = useAuth();

  const planStatus  = user?.plan_status || "free";
  const pageCount   = user?.page_count  || 0;
  const pageLimit   = getPlanLimit(planStatus);
  const pageBalance = getPageBalance(pageCount, planStatus);

  const plan: UserPlan = {
    planName:        getPlanDisplayName(planStatus),
    pageBalance,
    pageLimit,
    extraPages:      user?.extras_reported ?? Math.max(0, pageCount - pageLimit),
    email:           user?.email || "",
    role:            (user?.role as "user" | "admin") || "user",
    pageCount,
    planStatus,
    stripeCustomerId: user?.stripe_customer_id || null,
  };

  /**
   * Planos pagos (basic / standard / premium) podem sempre processar —
   * quando ultrapassam o limite incluído, as páginas extras são cobradas
   * automaticamente pelo Stripe. Nunca devem ser bloqueados.
   *
   * Free trial tem limite rígido de 50 páginas e não pode usar extras.
   */
  const canUseExtras = ACTIVE_PLANS.includes(planStatus);

  /**
   * Retorna true se o usuário pode consumir `count` páginas:
   * - Plano pago → sempre true (extras são cobráveis)
   * - Free trial → só se tiver saldo
   */
  const canConsume = (count: number): boolean =>
    canUseExtras || pageBalance >= count;

  return { plan, isLoading, canConsume, canUseExtras, refreshUser };
}
