// ============================================================
// CORREÇÃO 2: LoginPage.tsx
// Problema: sempre navegava para /app sem verificar o estado do plano.
// Fix: após login, verifica plan_status e page_count do usuário
// e redireciona adequadamente:
//   - admin        → /admin
//   - plano ativo  → /app
//   - free com saldo → /app
//   - free esgotado / past_due / sem plano → /#pricing
// ============================================================
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Mail, Lock, LogIn, ArrowLeft, MessageCircle } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const WHATSAPP_URL =
  "https://wa.me/5554999427282?text=Olá! Tenho dúvidas sobre o Sistema Ponto.";

const ACTIVE_PLANS = ["basic", "standard", "premium"];
const FREE_PAGE_LIMIT = 50;

const LoginPage = () => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();
  const { login, refreshUser } = useAuth();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error("Preencha todos os campos.");
      return;
    }
    setIsLoading(true);
    try {
      await login(email, password);

      // Busca os dados atualizados do usuário (agora vêm do DB, não só do JWT)
      // refreshUser já é chamado dentro de login(), então user estará populado
      // Decodifica o token para obter role e plan_status
      const token = localStorage.getItem("access_token");
      if (token) {
        try {
          const payload = token.split(".")[1];
          const decoded = JSON.parse(
            window.atob(payload.replace(/-/g, "+").replace(/_/g, "/"))
          );

          if (decoded.role === "admin") {
            navigate("/admin");
            return;
          }
        } catch {
          // Token inválido — deixa refreshUser decidir
        }
      }

      // Aguarda o user do contexto ser preenchido via refreshUser
      // Usa pequeno delay para garantir que o estado foi atualizado
      await new Promise((r) => setTimeout(r, 100));
      await refreshUser();

      // Lê o user atualizado via /api/user/me (que agora retorna do DB)
      const me = await fetch("/api/user/me", {
        headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
      }).then((r) => r.json());

      const planStatus: string = me?.plan_status ?? "free";
      const pageCount: number = me?.page_count ?? 0;

      if (me?.role === "admin") {
        navigate("/admin");
        return;
      }

      const hasActivePlan = ACTIVE_PLANS.includes(planStatus);
      const isFreeWithBalance =
        planStatus === "free" && pageCount < FREE_PAGE_LIMIT;

      if (hasActivePlan || isFreeWithBalance) {
        toast.success("Login realizado com sucesso!");
        navigate("/app");
      } else {
        // Usuário sem saldo ou com pagamento pendente
        const reason =
          planStatus === "past_due"
            ? "past_due"
            : "free_exhausted";
        toast.info(
          planStatus === "past_due"
            ? "Seu pagamento está pendente. Regularize para continuar."
            : "Suas páginas grátis foram utilizadas. Escolha um plano para continuar."
        );
        window.location.href = `/#pricing?reason=${reason}`;
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Erro ao fazer login.";
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  };

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
          <h2 className="text-2xl font-bold text-foreground">Entrar</h2>
          <p className="text-muted-foreground text-sm mt-2">
            Bem-vindo de volta ao Sistema Ponto
          </p>
        </div>

        <form onSubmit={handleLogin} className="flex flex-col gap-4">
          <div>
            <label className="text-sm font-medium text-foreground mb-2 block">
              E-mail
            </label>
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
            <label className="text-sm font-medium text-foreground mb-2 block">
              Senha
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-10 pr-4 py-3 bg-background/60 border border-border rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                required
                autoComplete="current-password"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="gradient-primary text-primary-foreground py-3 rounded-lg font-semibold flex items-center justify-center gap-2 hover:shadow-lg hover:shadow-primary/25 transition-all disabled:opacity-50 mt-2"
          >
            <LogIn className="w-4 h-4" />
            {isLoading ? "Entrando..." : "Entrar"}
          </button>
        </form>

        <p className="text-center text-muted-foreground text-sm mt-6">
          Não tem conta?{" "}
          <Link to="/cadastro" className="text-primary hover:underline font-medium">
            Cadastre-se grátis
          </Link>
        </p>

        <a
          href={WHATSAPP_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-2 mt-4 text-sm text-muted-foreground hover:text-success transition-colors"
        >
          <MessageCircle className="w-4 h-4" />
          Suporte via WhatsApp
        </a>
      </motion.div>
    </div>
  );
};

export default LoginPage;
