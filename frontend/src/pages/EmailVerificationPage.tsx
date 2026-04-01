// frontend/src/pages/EmailVerificationPage.tsx  (ARQUIVO NOVO)
//
// Rota: /verificar-email?token=<token>
// Chamada quando o usuário clica no link do email de verificação.

import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { CheckCircle, XCircle, Loader2, RefreshCw, Mail } from "lucide-react";
import { toast } from "sonner";

type Status = "loading" | "success" | "expired" | "invalid" | "error";

const EmailVerificationPage = () => {
  const [searchParams] = useSearchParams();
  const [status,        setStatus]        = useState<Status>("loading");
  const [resending,     setResending]     = useState(false);
  const [resendEmail,   setResendEmail]   = useState("");
  const [resendCooldown, setResendCooldown] = useState(0);

  const token = searchParams.get("token") ?? "";

  useEffect(() => {
    if (!token) { setStatus("invalid"); return; }

    const verify = async () => {
      try {
        const res  = await fetch(`/api/auth/verify-email?token=${encodeURIComponent(token)}`);
        const data = await res.json();

        if (res.ok && data.success) {
          setStatus("success");
        } else if (data.error_code === "TOKEN_EXPIRED") {
          setResendEmail(data.email ?? "");
          setStatus("expired");
        } else {
          setStatus("invalid");
        }
      } catch {
        setStatus("error");
      }
    };

    verify();
  }, [token]);

  const handleResend = async () => {
    if (!resendEmail || resendCooldown > 0) return;
    setResending(true);
    try {
      const res  = await fetch("/api/auth/resend-verification", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ email: resendEmail }),
      });
      const data = await res.json();

      if (res.status === 429) {
        setResendCooldown(data.retry_after ?? 60);
        const interval = setInterval(() => {
          setResendCooldown((c) => {
            if (c <= 1) { clearInterval(interval); return 0; }
            return c - 1;
          });
        }, 1000);
        toast.info(`Aguarde ${data.retry_after}s.`);
      } else {
        toast.success("Novo link enviado! Verifique seu email.");
      }
    } catch {
      toast.error("Erro ao reenviar. Tente novamente.");
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="min-h-screen gradient-bg flex items-center justify-center p-5">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5 }}
        className="glass-card p-10 w-full max-w-md text-center"
      >

        {/* ── Loading ─────────────────────────────────────────── */}
        {status === "loading" && (
          <>
            <Loader2 className="w-16 h-16 animate-spin text-primary mx-auto mb-6" />
            <h2 className="text-xl font-bold text-foreground mb-2">Verificando seu email...</h2>
            <p className="text-muted-foreground text-sm">Aguarde um momento.</p>
          </>
        )}

        {/* ── Sucesso ─────────────────────────────────────────── */}
        {status === "success" && (
          <>
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", stiffness: 200, damping: 15 }}
            >
              <CheckCircle className="w-20 h-20 text-success mx-auto mb-6" />
            </motion.div>
            <h2 className="text-2xl font-bold text-foreground mb-3">Email confirmado!</h2>
            <p className="text-muted-foreground text-sm mb-6">
              Sua conta está ativa. Suas <strong className="text-foreground">50 páginas grátis</strong> estão disponíveis.
            </p>
            <Link
              to="/login"
              className="block w-full py-3 rounded-xl gradient-primary text-primary-foreground font-bold text-sm hover:shadow-lg hover:shadow-primary/25 transition-all"
            >
              Fazer login →
            </Link>
          </>
        )}

        {/* ── Token expirado ───────────────────────────────────── */}
        {status === "expired" && (
          <>
            <div className="w-16 h-16 rounded-full bg-amber-500/15 flex items-center justify-center mx-auto mb-6">
              <Mail className="w-8 h-8 text-amber-500" />
            </div>
            <h2 className="text-xl font-bold text-foreground mb-3">Link expirado</h2>
            <p className="text-muted-foreground text-sm mb-6">
              Este link de verificação expirou (válido por 24h).
              Solicite um novo abaixo.
            </p>
            <button
              onClick={handleResend}
              disabled={resending || resendCooldown > 0}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl gradient-primary text-primary-foreground font-bold text-sm hover:shadow-lg hover:shadow-primary/25 transition-all disabled:opacity-50 mb-4"
            >
              <RefreshCw className={`w-4 h-4 ${resending ? "animate-spin" : ""}`} />
              {resendCooldown > 0
                ? `Reenviar em ${resendCooldown}s`
                : resending
                ? "Enviando..."
                : "Enviar novo link de verificação"}
            </button>
            <Link to="/login" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
              Voltar ao login
            </Link>
          </>
        )}

        {/* ── Token inválido / já usado ────────────────────────── */}
        {status === "invalid" && (
          <>
            <XCircle className="w-16 h-16 text-destructive mx-auto mb-6" />
            <h2 className="text-xl font-bold text-foreground mb-3">Link inválido</h2>
            <p className="text-muted-foreground text-sm mb-6">
              Este link de verificação é inválido ou já foi utilizado.
              Se sua conta ainda não está ativa, faça um novo cadastro.
            </p>
            <div className="flex gap-3">
              <Link
                to="/cadastro"
                className="flex-1 py-3 rounded-lg border border-border text-foreground text-sm font-medium text-center hover:bg-secondary/60 transition-all"
              >
                Novo cadastro
              </Link>
              <Link
                to="/login"
                className="flex-1 py-3 rounded-xl gradient-primary text-primary-foreground text-sm font-bold text-center hover:shadow-lg hover:shadow-primary/25 transition-all"
              >
                Login
              </Link>
            </div>
          </>
        )}

        {/* ── Erro genérico ────────────────────────────────────── */}
        {status === "error" && (
          <>
            <XCircle className="w-16 h-16 text-destructive mx-auto mb-6" />
            <h2 className="text-xl font-bold text-foreground mb-3">Erro ao verificar</h2>
            <p className="text-muted-foreground text-sm mb-6">
              Ocorreu um erro de conexão. Tente novamente em alguns instantes.
            </p>
            <button
              onClick={() => window.location.reload()}
              className="w-full py-3 rounded-xl gradient-primary text-primary-foreground font-bold text-sm hover:shadow-lg hover:shadow-primary/25 transition-all"
            >
              Tentar novamente
            </button>
          </>
        )}

      </motion.div>
    </div>
  );
};

export default EmailVerificationPage;
