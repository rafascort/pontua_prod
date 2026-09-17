// frontend/src/novo/SomenteAdmin.tsx
//
// Porta do modulo de Pericias enquanto ele esta' em testes.
//
// Mesma regra do EscolhaLayout: quem nao e' admin nao entra, e a checagem e'
// no `role` que vem do /api/user/me (banco), nao de nada guardado no
// navegador. Quem nao passa vai para /app, a tela normal do produto.

import { ReactElement } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

export default function SomenteAdmin({ children }: { children: ReactElement }) {
  const { user, isLoading } = useAuth();

  if (isLoading) return null;
  if (user?.role !== "admin") return <Navigate to="/app" replace />;
  return children;
}
