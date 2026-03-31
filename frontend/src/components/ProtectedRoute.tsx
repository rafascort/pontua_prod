// frontend/src/components/ProtectedRoute.tsx
//
// Regras de acesso:
//   admin           → sempre passa
//   basic / standard / premium (plano ativo) → sempre passa, mesmo sem saldo
//                     (páginas extras são cobráveis, não devem ser bloqueadas)
//   free com saldo  → passa (pageCount < 50)
//   free esgotado   → redireciona para /#pricing
//   past_due        → redireciona para /#pricing com aviso de pagamento pendente
//   inactive        → redireciona para /#pricing

import { Navigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

const ACTIVE_PLANS   = ["basic", "standard", "premium"];
const FREE_PAGE_LIMIT = 50;

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const { isAuthenticated, isLoading, user } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen gradient-bg flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-[3px] border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-muted-foreground text-sm">Carregando...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Admin passa sem restrição alguma
  if (user?.role === "admin") {
    return <>{children}</>;
  }

  const planStatus = user?.plan_status ?? "free";
  const pageCount  = user?.page_count  ?? 0;

  // ── Plano pago ativo → sempre permite (extras são cobráveis) ──────────
  if (ACTIVE_PLANS.includes(planStatus)) {
    return <>{children}</>;
  }

  // ── Free trial com saldo disponível → permite ─────────────────────────
  if (planStatus === "free" && pageCount < FREE_PAGE_LIMIT) {
    return <>{children}</>;
  }

  // ── Todos os outros casos → redireciona para pricing ──────────────────
  // free esgotado, past_due, inactive, etc.
  const reason =
    planStatus === "past_due" ? "past_due"
    : planStatus === "free"   ? "free_exhausted"
    :                           "no_plan";

  window.location.href = `/#pricing?reason=${reason}`;
  return null;
};

export default ProtectedRoute;
