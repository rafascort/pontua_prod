import { useEffect, useState } from "react";
import { useSearchParams, Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Lock, ArrowLeft, CheckCircle2, XCircle, Loader2, Eye, EyeOff, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

type TokenState = "checking" | "valid" | "expired" | "invalid";

const ResetPasswordPage = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get("token") ?? "";

  const [tokenState, setTokenState] = useState<TokenState>("checking");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!token) { setTokenState("invalid"); return; }
    (async () => {
      try {
        const res = await fetch(`/api/auth/verify-reset-token?token=${encodeURIComponent(token)}`);
        const data = await res.json().catch(() => ({}));
        if (res.ok && data.valid) { setTokenState("valid"); }
        else if (data.error_code === "TOKEN_EXPIRED") { setTokenState("expired"); }
        else { setTokenState("invalid"); }
      } catch { setTokenState("invalid"); }
    })();
  }, [token]);

  const checks = {
    length: password.length >= 6,
    number: /\d/.test(password),
    special: /[!@#$%^&*(),.?":{}|<>]/.test(password),
    match: password.length > 0 && password === confirmPassword,
  };
  const allValid = checks.length && checks.number && checks.special && checks.match;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!allValid) { toast.error("Verifique os requisitos da senha."); return; }
    setIsSubmitting(true);
    try {
      const res = await fetch("/api/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: password }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.success) {
        setDone(true);
        setTimeout(() => navigate("/login?reset=ok"), 2500);
      } else if (data.error_code === "TOKEN_EXPIRED") {
        setTokenState("expired");
      } else if (data.error_code === "INVALID_TOKEN") {
        setTokenState("invalid");
      } else {
        toast.error(data.msg || "Erro ao redefinir senha.");
      }
    } catch {
      toast.error("Erro de rede. Tente novamente.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen gradient-bg flex items-center justify-center p-5">
      <motion.div initial={{ opacity: 0, y: 20, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.5 }} className="glass-card p-10 w-full max-w-md relative">
        <Link to="/login" className="absolute top-4 left-4 flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="w-4 h-4" />
          Voltar ao login
        </Link>
        {tokenState === "checking" && (
          <div className="text-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-primary mx-auto mb-4" />
            <p className="text-muted-foreground text-sm">Validando link...</p>
          </div>
        )}
        {tokenState === "invalid" && (
          <div className="text-center mt-4">
            <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-destructive/10 border border-destructive/20 flex items-center justify-center">
              <XCircle className="w-6 h-6 text-destructive" />
            </div>
            <h2 className="text-2xl font-bold text-foreground mb-2">Link inválido</h2>
            <p className="text-muted-foreground text-sm leading-relaxed">
              Este link de redefinição não é válido ou já foi utilizado.
            </p>
            <Link to="/esqueci-senha" className="inline-block mt-6 px-6 py-2.5 rounded-lg gradient-primary text-primary-foreground text-sm font-semibold">
              Solicitar novo link
            </Link>
          </div>
        )}
        {tokenState === "expired" && (
          <div className="text-center mt-4">
            <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
              <XCircle className="w-6 h-6 text-amber-500" />
            </div>
            <h2 className="text-2xl font-bold text-foreground mb-2">Link expirado</h2>
            <p className="text-muted-foreground text-sm leading-relaxed">
              Os links de redefinição expiram após 1 hora por segurança. Solicite um novo.
            </p>
            <Link to="/esqueci-senha" className="inline-block mt-6 px-6 py-2.5 rounded-lg gradient-primary text-primary-foreground text-sm font-semibold">
              Solicitar novo link
            </Link>
          </div>
        )}
        {done && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center mt-4">
            <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-success/10 border border-success/20 flex items-center justify-center">
              <CheckCircle2 className="w-6 h-6 text-success" />
            </div>
            <h2 className="text-2xl font-bold text-foreground mb-2">Senha redefinida!</h2>
            <p className="text-muted-foreground text-sm">Redirecionando para o login...</p>
          </motion.div>
        )}
        {tokenState === "valid" && !done && (
          <>
            <div className="text-center mb-8 mt-4">
              <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center">
                <ShieldCheck className="w-6 h-6 text-primary" />
              </div>
              <h2 className="text-2xl font-bold text-foreground">Crie uma nova senha</h2>
              <p className="text-muted-foreground text-sm mt-2">
                Escolha uma senha forte que você não use em outros sites.
              </p>
            </div>
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <div>
                <label className="text-sm font-medium text-foreground mb-2 block">Nova senha</label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <input type={showPassword ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" className="w-full pl-10 pr-10 py-3 bg-background/60 border border-border rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all" required autoFocus autoComplete="new-password" />
                  <button type="button" onClick={() => setShowPassword((s) => !s)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
              <div>
                <label className="text-sm font-medium text-foreground mb-2 block">Confirme a nova senha</label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <input type={showPassword ? "text" : "password"} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="••••••••" className="w-full pl-10 pr-4 py-3 bg-background/60 border border-border rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all" required autoComplete="new-password" />
                </div>
              </div>
              <div className="space-y-1.5 text-xs mt-1">
                <Requirement ok={checks.length} label="Pelo menos 6 caracteres" />
                <Requirement ok={checks.number} label="Pelo menos 1 número" />
                <Requirement ok={checks.special} label="Pelo menos 1 caractere especial (!@#$%...)" />
                <Requirement ok={checks.match} label="As senhas coincidem" />
              </div>
              <button type="submit" disabled={!allValid || isSubmitting} className="gradient-primary text-primary-foreground py-3 rounded-lg font-semibold flex items-center justify-center gap-2 hover:shadow-lg hover:shadow-primary/25 transition-all disabled:opacity-50 mt-2">
                <ShieldCheck className="w-4 h-4" />
                {isSubmitting ? "Redefinindo..." : "Redefinir senha"}
              </button>
            </form>
          </>
        )}
      </motion.div>
    </div>
  );
};

const Requirement = ({ ok, label }: { ok: boolean; label: string }) => (
  <div className={`flex items-center gap-2 ${ok ? "text-success" : "text-muted-foreground"}`}>
    {ok ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5 opacity-40" />}
    <span>{label}</span>
  </div>
);

export default ResetPasswordPage;
