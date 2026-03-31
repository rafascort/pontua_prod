// ============================================================
// CORREÇÃO 5: PaymentSuccessPage.tsx  (ARQUIVO NOVO)
// Problema: /payment-success não existia no novo frontend.
// O backend usa essa URL como success_url no Stripe Checkout,
// então após pagar o usuário caía em 404.
// Fix: cria a página, atualiza os dados do usuário e redireciona
// para /app com mensagem de boas-vindas ao novo plano.
// ============================================================
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { CheckCircle, Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const PaymentSuccessPage = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { refreshUser } = useAuth();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");

  useEffect(() => {
    const init = async () => {
      // Aguarda um momento para que o webhook do Stripe processe
      await new Promise((r) => setTimeout(r, 2500));

      try {
        // Atualiza os dados do usuário — agora /api/user/me lê do DB
        await refreshUser();
        setStatus("success");

        // Redireciona para o app após exibir a mensagem de sucesso
        setTimeout(() => navigate("/app"), 2500);
      } catch {
        setStatus("error");
        setTimeout(() => navigate("/app"), 3000);
      }
    };

    init();
  }, [refreshUser, navigate]);

  const sessionId = searchParams.get("session_id");

  return (
    <div className="min-h-screen gradient-bg flex items-center justify-center p-5">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5 }}
        className="glass-card p-12 w-full max-w-md text-center"
      >
        {status === "loading" && (
          <>
            <Loader2 className="w-16 h-16 animate-spin text-primary mx-auto mb-6" />
            <h2 className="text-2xl font-bold text-foreground mb-3">
              Confirmando seu pagamento...
            </h2>
            <p className="text-muted-foreground text-sm">
              Aguarde enquanto ativamos seu plano. Isso pode levar alguns segundos.
            </p>
          </>
        )}

        {status === "success" && (
          <>
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", stiffness: 200, damping: 15 }}
            >
              <CheckCircle className="w-20 h-20 text-success mx-auto mb-6" />
            </motion.div>
            <h2 className="text-2xl font-bold text-foreground mb-3">
              Pagamento confirmado!
            </h2>
            <p className="text-muted-foreground text-sm mb-2">
              Seu plano foi ativado com sucesso.
            </p>
            <p className="text-muted-foreground text-xs">
              Redirecionando para o sistema...
            </p>
            {sessionId && (
              <p className="text-[10px] text-muted-foreground/50 mt-4 font-mono">
                Ref: {sessionId.slice(0, 20)}...
              </p>
            )}
          </>
        )}

        {status === "error" && (
          <>
            <CheckCircle className="w-16 h-16 text-primary mx-auto mb-6" />
            <h2 className="text-2xl font-bold text-foreground mb-3">
              Pagamento recebido!
            </h2>
            <p className="text-muted-foreground text-sm">
              Seu pagamento foi processado. O plano será ativado em instantes.
              Redirecionando...
            </p>
          </>
        )}
      </motion.div>
    </div>
  );
};

export default PaymentSuccessPage;
