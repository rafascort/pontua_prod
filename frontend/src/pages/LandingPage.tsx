import { motion } from "framer-motion";
import { FileText, CreditCard, Zap, Shield, ArrowRight, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

const features = [
  { icon: FileText, title: "Extração Inteligente", desc: "IA avançada para extrair dados de cartões ponto automaticamente." },
  { icon: Zap, title: "Processamento Rápido", desc: "Resultados em segundos, não horas. Economize tempo valioso." },
  { icon: Shield, title: "Dados Seguros", desc: "Seus documentos são processados com criptografia de ponta." },
];

const plans = [
  { name: "Free Trial", price: "Grátis", pages: "50 páginas", highlight: false, badge: "Bônus de cadastro" },
  { name: "Básico", price: "R$ 179,90", pages: "200 páginas/mês", highlight: false },
  { name: "Padrão", price: "R$ 349,90", pages: "500 páginas/mês", highlight: true },
  { name: "Premium", price: "R$ 699,90", pages: "Ilimitado", highlight: false },
];

const LandingPage = () => {
  return (
    <div className="min-h-screen gradient-bg">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-background/60 backdrop-blur-xl border-b border-border/30">
        <div className="container mx-auto flex items-center justify-between py-4 px-6">
          <h1 className="text-xl font-bold text-foreground">Sistema Ponto</h1>
          <nav className="flex items-center gap-4">
            <a href="#pricing" className="text-muted-foreground hover:text-foreground transition-colors text-sm">
              Planos
            </a>
            <Link to="/login" className="text-muted-foreground hover:text-foreground transition-colors text-sm">
              Login
            </Link>
            <Link
              to="/cadastro"
              className="gradient-primary text-primary-foreground px-5 py-2 rounded-lg text-sm font-semibold transition-all hover:shadow-[0_0_20px_rgba(74,158,255,0.3)]"
            >
              Cadastro
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="relative py-32 px-6 overflow-hidden">
        <div className="absolute inset-0 overflow-hidden">
          <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/5 rounded-full blur-3xl" />
          <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-primary/8 rounded-full blur-3xl" />
        </div>
        <div className="container mx-auto text-center relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
          >
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-primary/30 bg-primary/10 mb-8">
              <Sparkles className="w-4 h-4 text-primary" />
              <span className="text-sm text-primary font-medium">50 páginas grátis no cadastro</span>
            </div>
            <h2 className="text-5xl md:text-6xl font-extrabold text-foreground mb-6 leading-tight">
              Automatize o Ponto
              <br />
              <span className="text-gradient">com Inteligência Artificial</span>
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto mb-10">
              Economize horas na extração de dados de cartões ponto. Nossa IA processa seus PDFs
              e entrega resultados precisos em segundos.
            </p>
            <Link to="/cadastro">
              <motion.button
                whileHover={{ scale: 1.03, y: -2 }}
                whileTap={{ scale: 0.98 }}
                className="gradient-primary text-primary-foreground px-8 py-4 rounded-xl text-lg font-bold shadow-lg shadow-primary/25 inline-flex items-center gap-3 animate-glow-pulse"
              >
                Cadastre-se e ganhe 50 páginas grátis
                <ArrowRight className="w-5 h-5" />
              </motion.button>
            </Link>
          </motion.div>
        </div>
      </section>

      {/* Features */}
      <section className="py-24 px-6">
        <div className="container mx-auto">
          <h3 className="text-3xl font-bold text-center text-foreground mb-16">Por que escolher o Sistema Ponto?</h3>
          <div className="grid md:grid-cols-3 gap-8">
            {features.map((f, i) => (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.15 }}
                className="glass-card-hover p-8 text-center"
              >
                <div className="w-14 h-14 rounded-xl gradient-primary flex items-center justify-center mx-auto mb-5">
                  <f.icon className="w-7 h-7 text-primary-foreground" />
                </div>
                <h4 className="text-xl font-semibold text-foreground mb-3">{f.title}</h4>
                <p className="text-muted-foreground text-sm leading-relaxed">{f.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-24 px-6">
        <div className="container mx-auto">
          <h3 className="text-3xl font-bold text-center text-foreground mb-4">Planos e Preços</h3>
          <p className="text-center text-muted-foreground mb-16">Escolha o plano ideal para sua necessidade</p>
          <div className="grid md:grid-cols-4 gap-6 max-w-5xl mx-auto">
            {plans.map((p, i) => (
              <motion.div
                key={p.name}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className={`glass-card p-6 flex flex-col relative ${
                  p.highlight ? "glow-border" : ""
                }`}
              >
                {p.highlight && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full gradient-primary text-xs font-semibold text-primary-foreground">
                    Popular
                  </div>
                )}
                {p.badge && (
                  <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-success/20 text-success text-xs font-medium mb-3 w-fit">
                    <Sparkles className="w-3 h-3" />
                    {p.badge}
                  </div>
                )}
                <h4 className="text-lg font-semibold text-foreground">{p.name}</h4>
                <p className="text-3xl font-extrabold text-foreground mt-3">{p.price}</p>
                <p className="text-sm text-muted-foreground mt-1">{p.pages}</p>
                <div className="flex-1" />
                <Link to="/cadastro" className="mt-6">
                  <button
                    className={`w-full py-3 rounded-lg font-semibold text-sm transition-all ${
                      p.highlight
                        ? "gradient-primary text-primary-foreground hover:shadow-lg hover:shadow-primary/25"
                        : "bg-secondary text-secondary-foreground hover:bg-surface-hover"
                    }`}
                  >
                    {p.name === "Free Trial" ? "Cadastre-se e ganhe 50 páginas grátis" : "Assinar"}
                  </button>
                </Link>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border/30 py-8 px-6">
        <div className="container mx-auto flex items-center justify-between">
          <p className="text-muted-foreground text-sm">© 2026 Sistema Ponto. Todos os direitos reservados.</p>
          <div className="flex items-center gap-4">
            <Link to="/termos" className="text-muted-foreground hover:text-foreground text-sm transition-colors">
              Termos de Uso
            </Link>
            <div className="flex items-center gap-2">
              <CreditCard className="w-4 h-4 text-muted-foreground" />
              <span className="text-muted-foreground text-sm">Pagamento seguro</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
