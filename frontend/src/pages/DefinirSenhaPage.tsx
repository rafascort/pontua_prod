// frontend/src/pages/DefinirSenhaPage.tsx
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Building, ShieldCheck, AlertCircle, Loader2, Eye, EyeOff, Lock } from "lucide-react";

interface InviteInfo {
  email: string;
  org_name: string;
  org_role: string;
  is_admin: boolean;
}

export default function DefinirSenhaPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token") || "";

  const [info, setInfo] = useState<InviteInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token) {
      setError("Link invalido. Solicite um novo convite.");
      setLoading(false);
      return;
    }
    fetch(`/api/org/invite/${token}/info`)
      .then(async (r) => {
        const data = await r.json();
        if (r.ok) setInfo(data);
        else setError(data.msg || "Convite invalido.");
      })
      .catch(() => setError("Erro de rede ao validar convite."))
      .finally(() => setLoading(false));
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password.length < 8) {
      toast.error("Senha deve ter no minimo 8 caracteres.");
      return;
    }
    if (password !== confirm) {
      toast.error("As senhas nao coincidem.");
      return;
    }
    setSubmitting(true);
    try {
      const r = await fetch(`/api/org/invite/${token}/accept`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const data = await r.json();
      if (!r.ok) {
        toast.error(data.msg || "Erro ao definir senha.");
        return;
      }
      // Auto-login
      localStorage.setItem("access_token", data.access_token);
      toast.success("Senha definida! Bem-vindo ao Sistema Ponto.");
      // Admin da empresa vai pra /empresa, funcionario vai pra /app
      const dest = data.user?.org_role === "admin" ? "/empresa" : "/app";
      setTimeout(() => { window.location.href = dest; }, 800);
    } catch {
      toast.error("Erro de rede.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen gradient-bg flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error || !info) {
    return (
      <div className="min-h-screen gradient-bg flex items-center justify-center px-4">
        <div className="max-w-md w-full bg-card border border-border rounded-xl p-8 text-center">
          <AlertCircle className="w-12 h-12 mx-auto text-destructive mb-3" />
          <h2 className="text-xl font-semibold text-foreground mb-2">Convite invalido</h2>
          <p className="text-muted-foreground text-sm mb-5">{error}</p>
          <button onClick={() => navigate("/login")} className="px-4 py-2 rounded-lg gradient-primary text-primary-foreground text-sm">
            Ir para o login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen gradient-bg flex items-center justify-center px-4 py-8">
      <div className="max-w-md w-full bg-card border border-border rounded-xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-8 py-6 gradient-primary text-primary-foreground">
          <div className="flex items-center gap-2 text-xs opacity-90 mb-2">
            <ShieldCheck className="w-4 h-4" /> CONVITE PARA EMPRESA
          </div>
          <h1 className="text-2xl font-bold">Bem-vindo!</h1>
          <p className="text-sm opacity-90 mt-1">
            Voce foi convidado para <strong>{info.org_name}</strong> como{" "}
            <strong>{info.is_admin ? "Administrador" : "Funcionario"}</strong>.
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-8 space-y-4">
          <div>
            <label className="text-xs text-muted-foreground">Seu e-mail</label>
            <div className="mt-1 px-3 py-2 rounded-md bg-muted/30 border border-border/50 text-sm text-foreground">
              {info.email}
            </div>
          </div>

          <div>
            <label className="text-xs text-muted-foreground">Nova senha</label>
            <div className="relative mt-1">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type={showPw ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-muted/30 border border-border/50 rounded-md pl-10 pr-10 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                placeholder="Minimo 8 caracteres"
                required
                minLength={8}
                autoFocus
              />
              <button
                type="button"
                onClick={() => setShowPw(!showPw)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <div>
            <label className="text-xs text-muted-foreground">Confirmar senha</label>
            <div className="relative mt-1">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type={showPw ? "text" : "password"}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="w-full bg-muted/30 border border-border/50 rounded-md pl-10 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                placeholder="Digite novamente"
                required
                minLength={8}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full px-4 py-3 rounded-lg gradient-primary text-primary-foreground text-sm font-semibold disabled:opacity-50 mt-2"
          >
            {submitting ? "Definindo senha..." : "Definir senha e entrar"}
          </button>

          {info.is_admin && (
            <p className="text-xs text-muted-foreground text-center pt-2">
              Apos definir a senha, voce sera levado para a area da empresa para cadastrar o cartao de pagamento.
            </p>
          )}
        </form>
      </div>
    </div>
  );
}
