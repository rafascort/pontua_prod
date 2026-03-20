import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Mail, Lock, LogIn, ArrowLeft, MessageCircle } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const WHATSAPP_URL = "https://wa.me/5511999999999?text=Olá! Tenho dúvidas sobre o Sistema Ponto.";

const LoginPage = () => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();
  const { login } = useAuth();

  const handleLogin = async (e: React.FormEvent) => {
  e.preventDefault();
  if (!email || !password) {
    toast.error("Preencha todos os campos.");
    return;
  }
  setIsLoading(true);
  try {
    await login(email, password);
    
    // Decodifica o token para pegar o role (igual ao frontend antigo)
    const token = localStorage.getItem("access_token");
    if (token) {
      const base64Url = token.split('.')[1];
      const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
      const decoded = JSON.parse(window.atob(base64));
      
      if (decoded.role === "admin") {
        navigate("/admin");
      } else {
        navigate("/app");
      }
    } else {
      navigate("/app");
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
        <div className="text-center mb-8 mt-4">
          <h2 className="text-2xl font-bold text-foreground">Sistema Ponto</h2>
          <p className="text-muted-foreground text-sm mt-2">Acesse sua conta</p>
        </div>
        <form onSubmit={handleLogin} className="flex flex-col gap-5">
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
                placeholder="••••••••"
                className="w-full pl-10 pr-4 py-3 bg-background/60 border border-border rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                required
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={isLoading}
            className="gradient-primary text-primary-foreground py-3 rounded-lg font-semibold flex items-center justify-center gap-2 hover:shadow-lg hover:shadow-primary/25 transition-all disabled:opacity-50"
          >
            <LogIn className="w-4 h-4" />
            {isLoading ? "Entrando..." : "Entrar"}
          </button>
        </form>
        <p className="text-center text-muted-foreground text-sm mt-6">
          Não tem conta?{" "}
          <Link to="/cadastro" className="text-primary hover:underline font-medium">
            Cadastre-se
          </Link>
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

export default LoginPage;
