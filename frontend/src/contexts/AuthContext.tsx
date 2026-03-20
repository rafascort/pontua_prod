import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { api } from "@/lib/api";

interface UserData {
  id: number;
  email: string;
  role: string;
  is_active: boolean;
  page_count: number;
  plan_status: string;
  stripe_customer_id: string | null;
}

interface AuthContextType {
  user: UserData | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<string>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

const PLAN_LIMITS: Record<string, number> = {
  free: 50,
  basic: 200,
  standard: 500,
  premium: 1500,
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
  return PLAN_LIMITS[status] || 0;
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
      const data = await api.getUserDetails();
      setUser(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "";
      // Só desloga se for sessão expirada (401)
      if (message.includes("Sessão expirada") || message.includes("401")) {
        setUser(null);
      }
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

  const register = async (email: string, password: string) => {
    const result = await api.register(email, password);
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
