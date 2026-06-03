// frontend/src/pages/CadastroPage.tsx
import { useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Mail, Lock, Sparkles, UserPlus, ArrowLeft, MessageCircle, CheckCircle, RefreshCw, Users } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import {
  useReferralCapture,
  getStoredReferralCode,
  clearStoredReferralCode,
} from "@/hooks/useReferralCapture";

const WHATSAPP_URL =
  "https://wa.me/5554999427282?text=Olá! Tenho dúvidas sobre o Sistema Ponto.";

const CadastroPage = () => {
  // Captura ?ref=CODIGO da URL se presente
  useReferralCapture();

  const [email,           setEmail]           = useState("");
  const [password,        setPassword]        = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading,       setIsLoading]       = useState(false);
  const [emailSent,       setEmailSent]       = useState(false);        // estado pós-cadastro
  const [resending,       setResending]       = useState(false);
  const [resendCooldown,  setResendCooldown]  = useState(0);            // segundos restantes
  const [refCode] = useState<string | null>(() => getStoredReferralCode());
  const { register } = useAuth();

  const handleCadastro = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) { toast.error("As senhas não coincidem."); return; }
    if (password.length < 6) { toast.error("A senha deve ter pelo menos 6 caracteres."); return; }
    setIsLoading(true);
    try {
      await register(email, password, refCode);
      clearStoredReferralCode();
      // Não faz mais auto-login — aguarda confirmação de email
      setEmailSent(true);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Erro ao criar conta.";
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0) return;
    setResending(true);
    try {
      const res  = await fetch("/api/auth/resend-verification", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ email }),
      });
      const data = await res.json();

      if (res.status === 429) {
        setResendCooldown(data.retry_after ?? 60);
        // Inicia o countdown
        const interval = setInterval(() => {
          setResendCooldown((c) => {
            if (c <= 1) { clearInterval(interval); return 0; }
            return c - 1;
          });
        }, 1000);
        toast.info(`Aguarde ${data.retry_after}s antes de reenviar.`);
      } else {
        toast.success("Email reenviado! Verifique sua caixa de entrada.");
      }
    } catch {
      toast.error("Erro ao reenviar. Tente novamente.");
    } finally {
      setResending(false);
    }
  };

  // ── Estado pós-cadastro: email enviado ───────────────────────────────────
  if (emailSent) {
    return (
      <div className="min-h-screen gradient-bg flex items-center justify-center p-5">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5 }}
          className="glass-card p-10 w-full max-w-md text-center"
        >
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", stiffness: 200, damping: 15, delay: 0.1 }}
            className="w-20 h-20 rounded-full bg-primary/15 flex items-center justify-center mx-auto mb-6"
          >
            <Mail className="w-10 h-10 text-primary" />
          </motion.div>

          <h2 className="text-2xl font-bold text-foreground mb-3">Verifique seu email</h2>

          <p className="text-muted-foreground text-sm leading-relaxed mb-2">
            Enviamos um link de confirmação para:
          </p>
          <p className="font-semibold text-foreground mb-6 text-sm bg-secondary/50 px-4 py-2 rounded-lg inline-block">
            {email}
          </p>

          <div className="bg-primary/5 border border-primary/20 rounded-xl p-4 mb-6 text-left space-y-2">
            <p className="text-xs text-muted-foreground flex items-start gap-2">
              <CheckCircle className="w-3.5 h-3.5 text-success shrink-0 mt-0.5" />
              Clique no link do email para ativar sua conta
            </p>
            <p className="text-xs text-muted-foreground flex items-start gap-2">
              <CheckCircle className="w-3.5 h-3.5 text-success shrink-0 mt-0.5" />
              O link expira em 24 horas
            </p>
            <p className="text-xs text-muted-foreground flex items-start gap-2">
              <CheckCircle className="w-3.5 h-3.5 text-success shrink-0 mt-0.5" />
              Após confirmar, suas 50 páginas grátis estarão disponíveis
            </p>
          </div>

          {/* Botão de reenvio */}
          <button
            onClick={handleResend}
            disabled={resending || resendCooldown > 0}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-lg border border-border text-foreground text-sm font-medium hover:bg-secondary/60 transition-all disabled:opacity-50 mb-4"
          >
            <RefreshCw className={`w-4 h-4 ${resending ? "animate-spin" : ""}`} />
            {resendCooldown > 0
              ? `Reenviar em ${resendCooldown}s`
              : resending
              ? "Reenviando..."
              : "Reenviar email de verificação"}
          </button>

          <p className="text-xs text-muted-foreground mb-4">
            Não recebeu? Verifique a pasta de spam.
          </p>

          <Link to="/login" className="text-primary hover:underline text-sm font-medium">
            Já confirmei — ir para o login →
          </Link>
        </motion.div>
      </div>
    );
  }

  // ── Formulário de cadastro ───────────────────────────────────────────────
  return (
    <div className="min-h-screen gradient-bg flex items-center justify-center p-5">
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5 }}
        className="glass-card p-10 w-full max-w-md relative"
      >
        <Link
          to="/"
          className="absolute top-4 left-4 flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Voltar
        </Link>

        <div className="text-center mb-8">
          <h2 className="text-2xl font-bold text-foreground">Criar Conta</h2>
          <div className="inline-flex items-center gap-2 mt-3 px-4 py-1.5 rounded-full bg-success/15 border border-success/30">
            <Sparkles className="w-4 h-4 text-success" />
            <span className="text-sm text-success font-medium">Ganhe 50 páginas grátis!</span>
          </div>
        </div>

        {/* Banner de indicação — só aparece se tiver ?ref=CODIGO na URL */}
        {refCode && (
          <div className="mb-5 px-4 py-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
            <p className="text-xs text-emerald-700 dark:text-emerald-400 flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5" />
              Você foi convidado! Indicação{" "}
              <strong className="font-mono">{refCode.slice(0, 3)}***</strong>
            </p>
          </div>
        )}

        <form onSubmit={handleCadastro} className="flex flex-col gap-4">
          <div>
            <label className="text-sm font-medium text-foreground mb-2 block">E-mail</label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="seu@email.com"
                className="w-full pl-10 pr-4 py-3 bg-background/60 border border-border rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                required
                autoComplete="email"
              />
            </div>
          </div>

          <div>
            <label className="text-sm font-medium text-foreground mb-2 block">Senha</label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Mínimo 6 caracteres"
                className="w-full pl-10 pr-4 py-3 bg-background/60 border border-border rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                required
                autoComplete="new-password"
              />
            </div>
          </div>

          <div>
            <label className="text-sm font-medium text-foreground mb-2 block">Confirmar Senha</label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-10 pr-4 py-3 bg-background/60 border border-border rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                required
                autoComplete="new-password"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="gradient-primary text-primary-foreground py-3 rounded-lg font-semibold flex items-center justify-center gap-2 hover:shadow-lg hover:shadow-primary/25 transition-all disabled:opacity-50 mt-2"
          >
            <UserPlus className="w-4 h-4" />
            {isLoading ? "Criando conta..." : "Cadastre-se e ganhe 50 páginas grátis"}
          </button>
        </form>

        <p className="text-center text-muted-foreground text-sm mt-6">
          Já tem conta?{" "}
          <Link to="/login" className="text-primary hover:underline font-medium">Login</Link>
        </p>

        <a
          href={WHATSAPP_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-2 mt-4 text-sm text-muted-foreground hover:text-success transition-colors"
        >
          <MessageCircle className="w-4 h-4" />
          Entre em contato pelo WhatsApp
        </a>
      </motion.div>
    </div>
  );
};

export default CadastroPage;
