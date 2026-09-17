// frontend/src/novo/EntradaApp.tsx
//
// Porta de entrada do /app.
//
// O redirect do LoginPage sozinho nao basta: quem ja' tem sessao viva no
// navegador nunca passa pela tela de login, e caia onde caisse continuava na
// "Escolha o Serviço". Como o localStorage e' por origem, isso acontecia em
// sistemaponto.com e nao em sistemaponto.com.br, dando a impressao de que os
// dois dominios serviam coisas diferentes — servem o mesmo arquivo.
//
// Aqui a decisao e' por rota, entao vale para qualquer forma de chegar:
// atalho, sessao antiga, clique no logo do cabecalho.
//
// Cliente nenhum e' afetado: quem nao e' admin continua vendo a mesma tela.

import { Navigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import ServiceSelectionPage from "@/pages/ServiceSelectionPage";

export default function EntradaApp() {
  const { user, isLoading } = useAuth();

  if (isLoading) return null;
  if (user?.role === "admin") return <Navigate to="/pericias" replace />;
  return <ServiceSelectionPage />;
}
