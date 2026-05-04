import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Mail, Lock, LogIn, ArrowLeft, MessageCircle, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const WHATSAPP_URL = "https://wa.me/5554999427282?text=Olá! Tenho dúvidas sobre o Sistema Ponto.";
const ACTIVE_PLANS = ["basic", "standard", "premium"];
const FREE_PAGE_LIMIT = 50;

const LoginPage = () => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [notVerified, setNotVerified] = useState(false);
  const [unverifiedEmail, setUnverifiedEmail] = useState("");
  const [resending, setResending] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);

  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { login, refreshUser } = useAuth();

  const verified = searchParams.get("verified");
  if (verified === "true" && !isLoading) {
    setTimeout(() => toast.success("Email confirmado! Faça login para continuar."), 100);
  }

  const resetOk = searchParams.get("reset");
  if (resetOk === "ok" && !isLoading) {
    setTimeout(() => toast.success("Senha redefinida! Faça login com a nova senha."), 100);
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) { toast.error("Preencha todos os campos."); return; }
    setIsLoading(true);
    setNotVerified(false);
    try {
      await login(email, password);
      await refreshUser();
      const me = await fetch("/api/user/me", {
        headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
      }).then((r) => r.json());
      const planStatus: string = me?.plan_status ?? "free";
      const pageCount: number = me?.page_count ?? 0;
      if (me?.role === "admin") { navigate("/admin"); return; }
      const hasActivePlan = ACTIVE_PLANS.includes(planStatus);
      const isFreeWithBalance = planStatus === "free" && pageCount < FREE_PAGE_LIMIT;
      if (hasActivePlan || isFreeWithBalance) {
        toast.success("Bem-vindo de volta!");
        navigate("/app");
      } else {
        const reason = planStatus === "past_due" ? "past_due" : "free_exhausted";
        toast.info(planStatus === "past_due" ? "Seu pagamento está pendente. Regularize para continuar." : "Suas páginas grátis foram utilizadas. Assine um plano para continuar.");
        window.location.href = `/#pricing?reason=${reason}`;
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "";
      if (message.includes("EMAIL_NOT_VERIFIED") || message.includes("Confirme seu email")) {
        setNotVerified(true);
        setUnverifiedEmail(email);
      } else {
        toast.error(message || "Email ou senha inválidos.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0) return;
    setResending(true);
    try {
      const res = await fetch("/api/auth/resend-verification", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: unverifiedEmail }),
      });
      const data = await res.json();
      if (res.status === 429) {
        setResendCooldown(data.retry_after ?? 60);
        const interval = setInterval(() => {
          setResendCooldown((c) => { if (c <= 1) { clearInterval(interval); return 0; } return c - 1; });
        }, 1000);
        toast.info(`Aguarde ${data.retry_after}s.`);
      } else {
        toast.success("Email reenviado! Verifique sua caixa de entrada (e spam).");
      }
    } catch {
      toast.error("Erro ao reenviar. Tente novamente.");
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="min-h-screen gradient-bg flex items-center justify-center p-5">
      <motion.div initial={{ opacity: 0, y: 20, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.5 }} className="glass-card p-10 w-full max-w-md relative">
        <Link to="/" className="absolute top-4 left-4 flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="w-4 h-4" />
          Voltar
        </Link>
        <div className="text-center mb-8">
          <h2 className="text-2xl font-bold text-foreground">Entrar</h2>
          <p className="text-muted-foreground text-sm mt-2">Bem-vindo de volta ao Sistema Ponto</p>
        </div>
        {notVerified && (
          <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-6 p-4 rounded-xl bg-amber-500/10 border border-amber-500/30">
            <p className="text-sm font-semibold text-amber-500 mb-1">Email não confirmado</p>
            <p className="text-xs text-muted-foreground mb-3">
              Confirme seu email antes de fazer login. Verifique a caixa de entrada de <strong>{unverifiedEmail}</strong> (e a pasta de spam).
            </p>
            <button onClick={handleResend} disabled={resending || resendCooldown > 0} className="flex items-center gap-2 text-xs font-semibold text-amber-500 hover:text-amber-400 transition-colors disabled:opacity-50">
              <RefreshCw className={`w-3.5 h-3.5 ${resending ? "animate-spin" : ""}`} />
              {resendCooldown > 0 ? `Reenviar em ${resendCooldown}s` : resending ? "Enviando..." : "Reenviar email de verificação"}
            </button>
          </motion.div>
        )}
        <form onSubmit={handleLogin} className="flex flex-col gap-4">
          <div>
            <label className="text-sm font-medium text-foreground mb-2 block">E-mail</label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="seu@email.com" className="w-full pl-10 pr-4 py-3 bg-background/60 border border-border rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all" required autoComplete="email" />
            </div>
          </div>
          <div>
            <label className="text-sm font-medium text-foreground mb-2 block">Senha</label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" className="w-full pl-10 pr-4 py-3 bg-background/60 border border-border rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all" required autoComplete="current-password" />
            </div>
          </div>
          <div className="flex justify-end -mt-2">
            <Link to="/esqueci-senha" className="text-xs text-primary hover:underline font-medium">Esqueci minha senha</Link>
          </div>
          <button type="submit" disabled={isLoading} className="gradient-primary text-primary-foreground py-3 rounded-lg font-semibold flex items-center justify-center gap-2 hover:shadow-lg hover:shadow-primary/25 transition-all disabled:opacity-50 mt-2">
            <LogIn className="w-4 h-4" />
            {isLoading ? "Entrando..." : "Entrar"}
          </button>
        </form>
        <p className="text-center text-muted-foreground text-sm mt-6">
          Não tem conta?{" "}
          <Link to="/cadastro" className="text-primary hover:underline font-medium">Cadastre-se grátis</Link>
        </p>
        <a href={WHATSAPP_URL} target="_blank" rel="noopener noreferrer" className="flex items-center justify-center gap-2 mt-4 text-sm text-muted-foreground hover:text-success transition-colors">
          <MessageCircle className="w-4 h-4" />
          Suporte via WhatsApp
        </a>
      </motion.div>
    </div>
  );
};

export default LoginPage;
