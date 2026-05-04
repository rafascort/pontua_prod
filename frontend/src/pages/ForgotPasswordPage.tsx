import { useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Mail, ArrowLeft, MessageCircle, CheckCircle2, Send } from "lucide-react";
import { toast } from "sonner";

const WHATSAPP_URL = "https://wa.me/5554999427282?text=Olá! Tenho dúvidas sobre o Sistema Ponto.";

const ForgotPasswordPage = () => {
  const [email, setEmail] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) { toast.error("Digite seu email."); return; }
    setIsLoading(true);
    try {
      const res = await fetch("/api/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      });
      await res.json().catch(() => ({}));
      setSent(true);
    } catch {
      toast.error("Erro de rede. Tente novamente.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen gradient-bg flex items-center justify-center p-5">
      <motion.div initial={{ opacity: 0, y: 20, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.5 }} className="glass-card p-10 w-full max-w-md relative">
        <Link to="/login" className="absolute top-4 left-4 flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="w-4 h-4" />
          Voltar ao login
        </Link>
        {!sent ? (
          <>
            <div className="text-center mb-8 mt-4">
              <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center">
                <Mail className="w-6 h-6 text-primary" />
              </div>
              <h2 className="text-2xl font-bold text-foreground">Esqueceu a senha?</h2>
              <p className="text-muted-foreground text-sm mt-2">
                Digite seu email e enviaremos um link para redefinir sua senha.
              </p>
            </div>
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <div>
                <label className="text-sm font-medium text-foreground mb-2 block">E-mail</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="seu@email.com" className="w-full pl-10 pr-4 py-3 bg-background/60 border border-border rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all" required autoComplete="email" autoFocus />
                </div>
              </div>
              <button type="submit" disabled={isLoading} className="gradient-primary text-primary-foreground py-3 rounded-lg font-semibold flex items-center justify-center gap-2 hover:shadow-lg hover:shadow-primary/25 transition-all disabled:opacity-50 mt-2">
                <Send className="w-4 h-4" />
                {isLoading ? "Enviando..." : "Enviar link de redefinição"}
              </button>
            </form>
            <p className="text-center text-muted-foreground text-sm mt-6">
              Lembrou a senha?{" "}
              <Link to="/login" className="text-primary hover:underline font-medium">Fazer login</Link>
            </p>
          </>
        ) : (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="text-center mt-4">
            <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-success/10 border border-success/20 flex items-center justify-center">
              <CheckCircle2 className="w-6 h-6 text-success" />
            </div>
            <h2 className="text-2xl font-bold text-foreground mb-2">Verifique seu email</h2>
            <p className="text-muted-foreground text-sm leading-relaxed">
              Se o email <strong className="text-foreground">{email}</strong> estiver cadastrado, você receberá um link para redefinir sua senha em instantes.
            </p>
            <p className="text-muted-foreground text-xs mt-4">
              O link expira em <strong>1 hora</strong>. Não esqueça de checar a pasta de spam.
            </p>
            <Link to="/login" className="inline-block mt-6 px-6 py-2.5 rounded-lg border border-border text-sm text-foreground hover:bg-muted/40 transition-all">
              Voltar ao login
            </Link>
          </motion.div>
        )}
        <a href={WHATSAPP_URL} target="_blank" rel="noopener noreferrer" className="flex items-center justify-center gap-2 mt-6 text-sm text-muted-foreground hover:text-success transition-colors">
          <MessageCircle className="w-4 h-4" />
          Suporte via WhatsApp
        </a>
      </motion.div>
    </div>
  );
};

export default ForgotPasswordPage;
