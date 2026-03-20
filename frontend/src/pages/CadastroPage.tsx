import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Mail, Lock, Sparkles, UserPlus, ArrowLeft, MessageCircle } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const WHATSAPP_URL = "https://wa.me/5511999999999?text=Olá! Tenho dúvidas sobre o Sistema Ponto.";

const CadastroPage = () => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();
  const { register } = useAuth();

  const handleCadastro = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      toast.error("As senhas não coincidem.");
      return;
    }
    if (password.length < 6) {
      toast.error("A senha deve ter pelo menos 6 caracteres.");
      return;
    }
    setIsLoading(true);
    try {
      await register(email, password);
      toast.success("Conta criada! Você ganhou 50 páginas grátis. Redirecionando...");
      setTimeout(() => navigate("/login"), 1500);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Erro ao criar conta.";
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
          <h2 className="text-2xl font-bold text-foreground">Criar Conta</h2>
          <div className="inline-flex items-center gap-2 mt-3 px-4 py-1.5 rounded-full bg-success/15 border border-success/30">
            <Sparkles className="w-4 h-4 text-success" />
            <span className="text-sm text-success font-medium">Ganhe 50 páginas grátis!</span>
          </div>
        </div>
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
          <Link to="/login" className="text-primary hover:underline font-medium">
            Login
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

export default CadastroPage;
