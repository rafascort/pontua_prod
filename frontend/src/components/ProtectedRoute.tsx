// frontend/src/components/ProtectedRoute.tsx
//
// Regras:
//   admin do sistema             → sempre passa
//   usuário de empresa           → sempre passa (backend bloqueia se empresa suspensa)
//   plano pago (basic/std/prem)  → sempre passa
//   free com saldo               → passa
//   free esgotado / past_due     → redireciona para /#pricing

import { Navigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

const ACTIVE_PLANS = ["basic", "standard", "premium"];
const FREE_PAGE_LIMIT = 50;

// Le claims diretamente do JWT (mais confiavel que /api/user/me)
function jwtClaims(): any {
  try {
    const token = localStorage.getItem("access_token");
    if (!token) return {};
    const payload = token.split(".")[1];
    return JSON.parse(atob(payload));
  } catch { return {}; }
}

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

  // ── Admin do sistema sempre passa ─────────────────────────────────────
  if (user?.role === "admin") {
    return <>{children}</>;
  }

  // ── Usuário de empresa sempre passa ───────────────────────────────────
  // Empresa em past_due/suspended/etc é tratada no backend (retorna 403 ao processar)
  const claims = jwtClaims();
  if (claims.organization_id) {
    return <>{children}</>;
  }

  const planStatus = user?.plan_status ?? "free";
  const pageCount  = user?.page_count  ?? 0;

  if (ACTIVE_PLANS.includes(planStatus)) {
    return <>{children}</>;
  }

  if (planStatus === "free" && pageCount < FREE_PAGE_LIMIT) {
    return <>{children}</>;
  }

  const reason =
    planStatus === "past_due" ? "past_due"
    : planStatus === "free"   ? "free_exhausted"
    :                           "no_plan";

  window.location.href = `/#pricing?reason=${reason}`;
  return null;
};

export default ProtectedRoute;
