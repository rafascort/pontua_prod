// ============================================================
// CORREÇÃO 8: AuthContext.tsx
// Problema: refreshUser fazia logout em qualquer erro de rede,
// incluindo timeouts ou erros 5xx — deslogando usuário à toa.
// Fix: só desloga em erro 401 (sessão expirada) — outros erros
// são silenciados para não interromper a sessão do usuário.
// ============================================================
import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import { api } from "@/lib/api";

interface UserData {
  id: number;
  email: string;
  role: string;
  is_active: boolean;
  page_count: number;
  plan_status: string;
  stripe_customer_id: string | null;
  referral_code: string | null;        
  discount_credits: number;              
  extras_reported: number;
}

interface AuthContextType {
  user: UserData | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, refCode?: string | null) => Promise<string>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

// Limites por plan_status — usados para calcular saldo
const PLAN_LIMITS: Record<string, number> = {
  free: 50,
  basic: 200,
  standard: 500,
  premium: 1500,
  past_due: 0,
  inactive: 0,
};

export function getPlanDisplayName(status: string): string {
  const map: Record<string, string> = {
    free: "Free Trial",
    basic: "Básico",
    standard: "Padrão",
    premium: "Premium",
    past_due: "Pagamento Pendente",
    inactive: "Inativo",
  };
  return map[status] || status;
}

export function getPlanLimit(status: string): number {
  return PLAN_LIMITS[status] ?? 0;
}

export function getPageBalance(pageCount: number, planStatus: string): number {
  const limit = getPlanLimit(planStatus);
  return Math.max(0, limit - pageCount);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserData | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    try {
      // api.getUserDetails() chama /api/user/me — após a correção
      // do backend, plan_status vem do DB (não do JWT stale)
      const data = await api.getUserDetails();
      setUser(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "";
      // Só desloga se for sessão expirada (401) — não em erros de rede
      if (
        message.includes("Sessão expirada") ||
        message.includes("401") ||
        message.includes("Faça login")
      ) {
        setUser(null);
      }
      // Outros erros (500, timeout, offline) → mantém o user atual
    }
  }, []);

  useEffect(() => {
    if (api.isAuthenticated()) {
      refreshUser().finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, [refreshUser]);

  const login = async (email: string, password: string) => {
    await api.login(email, password);
    await refreshUser();
  };

  const register = async (email: string, password: string, refCode?: string | null) => {
    const result = await api.register(email, password, refCode);
    return result.msg;
  };

  const logout = () => {
    setUser(null);
    api.logout();
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
