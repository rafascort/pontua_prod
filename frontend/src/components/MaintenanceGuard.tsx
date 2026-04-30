// frontend/src/components/MaintenanceGuard.tsx
//
// Wrapper que protege rotas autenticadas durante manutenção.
// Se há manutenção ativa E o usuário NÃO é admin, redireciona para /manutencao.
// Admin vê tudo normal (com banner amarelo via AppHeader).

import { useEffect } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useMaintenance } from "@/hooks/useMaintenance";
import { useAuth } from "@/contexts/AuthContext";

interface Props {
  children: React.ReactNode;
}

const MaintenanceGuard = ({ children }: Props) => {
  const { status, isLoading } = useMaintenance();
  const { user } = useAuth();
  const location = useLocation();

  // Aguarda primeiro check de status
  if (isLoading) return null;

  // Sem manutenção → renderiza normalmente
  if (!status.active) return <>{children}</>;

  // Admin passa mesmo durante manutenção
  if (user?.role === "admin") return <>{children}</>;

  // Está na própria página de manutenção, deixa renderizar
  if (location.pathname === "/manutencao") return <>{children}</>;

  // Usuário comum durante manutenção → redireciona
  return <Navigate to="/manutencao" replace />;
};

export default MaintenanceGuard;
