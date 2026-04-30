// frontend/src/App.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/contexts/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import MaintenanceGuard from "@/components/MaintenanceGuard";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import CadastroPage from "./pages/CadastroPage";
import EmailVerificationPage from "./pages/EmailVerificationPage";
import ServiceSelectionPage from "./pages/ServiceSelectionPage";
import PontoExtractorPage from "./pages/PontoExtractorPage";
import HoleriteExtractorPage from "./pages/HoleriteExtractorPage";
import PaymentSuccessPage from "./pages/PaymentSuccessPage";
import TermosPage from "./pages/TermosPage";
import AdminPage from "./pages/AdminPage";
import MinhasIndicacoes from "./pages/MinhasIndicacoes";
import PromocoesPage from "./pages/PromocoesPage";
import MaintenancePage from "./pages/MaintenancePage";
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
            <Route path="/"          element={<LandingPage />} />
            <Route path="/login"     element={<LoginPage />} />
            <Route path="/cadastro"  element={<CadastroPage />} />
            <Route path="/termos"    element={<TermosPage />} />

            {/* Tela de manutenção (pública) */}
            <Route path="/manutencao" element={<MaintenancePage />} />

            {/* Verificação de email — chamada pelo link no email */}
            <Route path="/verificar-email" element={<EmailVerificationPage />} />

            {/* Stripe: /planos redireciona para a landing com pricing */}
            <Route path="/planos" element={<LandingPage scrollToPricing />} />

            {/* Protegidas — bloqueadas durante manutenção (exceto admin) */}
            <Route path="/app"
              element={
                <ProtectedRoute>
                  <MaintenanceGuard>
                    <ServiceSelectionPage />
                  </MaintenanceGuard>
                </ProtectedRoute>
              }
            />
            <Route path="/app/ponto"
              element={
                <ProtectedRoute>
                  <MaintenanceGuard>
                    <PontoExtractorPage />
                  </MaintenanceGuard>
                </ProtectedRoute>
              }
            />
            <Route path="/app/holerite"
              element={
                <ProtectedRoute>
                  <MaintenanceGuard>
                    <HoleriteExtractorPage />
                  </MaintenanceGuard>
                </ProtectedRoute>
              }
            />

            {/* Indicações e Promoções — também bloqueadas */}
            <Route path="/indicacoes"
              element={
                <ProtectedRoute>
                  <MaintenanceGuard>
                    <MinhasIndicacoes />
                  </MaintenanceGuard>
                </ProtectedRoute>
              }
            />
            <Route path="/promocoes"
              element={
                <ProtectedRoute>
                  <MaintenanceGuard>
                    <PromocoesPage />
                  </MaintenanceGuard>
                </ProtectedRoute>
              }
            />

            {/* Stripe: após pagamento bem-sucedido (não bloqueia) */}
            <Route path="/payment-success"
              element={<ProtectedRoute><PaymentSuccessPage /></ProtectedRoute>} />

            {/* Admin — NÃO usa MaintenanceGuard (admin sempre acessa) */}
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
