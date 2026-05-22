// frontend/src/pages/EmpresaPaymentSuccessPage.tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle2, Loader2 } from "lucide-react";

export default function EmpresaPaymentSuccessPage() {
  const navigate = useNavigate();
  const [active, setActive] = useState(false);
  const [polling, setPolling] = useState(true);

  // Faz polling de /api/org/me ate empresa virar 'active' (max 10 tentativas)
  useEffect(() => {
    let attempts = 0;
    const interval = setInterval(async () => {
      attempts++;
      try {
        const r = await fetch("/api/org/me", {
          headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
        });
        if (r.ok) {
          const data = await r.json();
          if (data.organization?.plan_status === "active" || data.organization?.stripe_customer_id) {
            setActive(true);
            setPolling(false);
            clearInterval(interval);
            return;
          }
        }
      } catch {}
      if (attempts >= 10) {
        setPolling(false);
        clearInterval(interval);
      }
    }, 1500);
    return () => clearInterval(interval);
  }, []);

  // Auto-redirect 3s apos ativar
  useEffect(() => {
    if (!active) return;
    const t = setTimeout(() => navigate("/empresa", { replace: true }), 3000);
    return () => clearTimeout(t);
  }, [active, navigate]);

  return (
    <div className="min-h-screen gradient-bg flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-card border border-border rounded-xl shadow-2xl p-8 text-center">
        {polling && !active ? (
          <>
            <Loader2 className="w-12 h-12 animate-spin text-primary mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-foreground mb-2">Confirmando pagamento...</h2>
            <p className="text-muted-foreground text-sm">
              Estamos confirmando o cadastro do cartao com o Stripe. Isso leva alguns segundos.
            </p>
          </>
        ) : active ? (
          <>
            <CheckCircle2 className="w-16 h-16 text-emerald-500 mx-auto mb-4" />
            <h2 className="text-2xl font-semibold text-foreground mb-2">Empresa ativada!</h2>
            <p className="text-muted-foreground text-sm mb-6">
              Cartao cadastrado com sucesso. Sua empresa esta ativa e funcionarios ja podem processar PDFs. Voce sera redirecionado em 3s...
            </p>
            <button
              onClick={() => navigate("/empresa", { replace: true })}
              className="px-5 py-2.5 rounded-lg gradient-primary text-primary-foreground text-sm font-medium"
            >
              Ir para a area da empresa
            </button>
          </>
        ) : (
          <>
            <CheckCircle2 className="w-16 h-16 text-emerald-500 mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-foreground mb-2">Pagamento recebido</h2>
            <p className="text-muted-foreground text-sm mb-6">
              O Stripe esta processando seu cadastro. Pode levar um minuto para refletir.
            </p>
            <button
              onClick={() => navigate("/empresa", { replace: true })}
              className="px-5 py-2.5 rounded-lg gradient-primary text-primary-foreground text-sm font-medium"
            >
              Ir para a area da empresa
            </button>
          </>
        )}
      </div>
    </div>
  );
}
