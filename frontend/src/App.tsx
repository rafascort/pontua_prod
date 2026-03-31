// ============================================================
// CORREÇÃO 6: App.tsx
// Problemas:
//   1. /payment-success não existia → 404 após pagamento Stripe
//   2. /planos não existia → 404 quando checkout era cancelado
// Fix: adiciona ambas as rotas + importa PaymentSuccessPage
// ============================================================
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/contexts/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import CadastroPage from "./pages/CadastroPage";
import ServiceSelectionPage from "./pages/ServiceSelectionPage";
import PontoExtractorPage from "./pages/PontoExtractorPage";
import HoleriteExtractorPage from "./pages/HoleriteExtractorPage";
import PaymentSuccessPage from "./pages/PaymentSuccessPage"; // ← NOVO
import TermosPage from "./pages/TermosPage";
import AdminPage from "./pages/AdminPage";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Sonner />
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            {/* Públicas */}
            <Route path="/" element={<LandingPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/cadastro" element={<CadastroPage />} />
            <Route path="/termos" element={<TermosPage />} />

            {/* Protegidas */}
            <Route
              path="/app"
              element={
                <ProtectedRoute>
                  <ServiceSelectionPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/ponto"
              element={
                <ProtectedRoute>
                  <PontoExtractorPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/holerite"
              element={
                <ProtectedRoute>
                  <HoleriteExtractorPage />
                </ProtectedRoute>
              }
            />

            {/* Stripe: após pagamento bem-sucedido */}
            {/* CORREÇÃO: rota /payment-success agora existe */}
            <Route
              path="/payment-success"
              element={
                <ProtectedRoute>
                  <PaymentSuccessPage />
                </ProtectedRoute>
              }
            />

            {/* Stripe: quando o usuário cancela o checkout */}
            {/* /planos redireciona de volta para a landing com a seção de preços */}
            <Route
              path="/planos"
              element={<LandingPage scrollToPricing />}
            />

            {/* Admin */}
            <Route path="/admin" element={<AdminPage />} />

            {/* 404 */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
