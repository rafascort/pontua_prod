// frontend/src/pages/LandingPage.tsx
import { useEffect } from "react";
import { motion } from "framer-motion";
import { FileText, Zap, Shield, ArrowRight, Sparkles, ChevronDown, CreditCard, LogOut, Settings } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useUserPlan } from "@/hooks/useUserPlan";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { api } from "@/lib/api";
import { toast } from "sonner";

const ACTIVE_PLANS = ["basic", "standard", "premium"];
const FREE_PAGE_LIMIT = 50;

// ─────────────────────────────────────────────────────────────
// Mini menu do usuário — igual ao AppHeader, mas dentro da landing
// ─────────────────────────────────────────────────────────────
const LandingUserMenu = () => {
  const { plan } = useUserPlan();
  const { logout } = useAuth();
  const navigate = useNavigate();

  const userEmail = plan.email || "";
  const initials  = userEmail.substring(0, 2).toUpperCase();

  const handleManageSubscription = async () => {
    if (plan.planStatus === "free" || plan.planStatus === "past_due") {
      window.location.href = "/#pricing";
      return;
    }
    try {
      const token    = localStorage.getItem("access_token");
      const response = await fetch("/api/create-portal-session", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      });
      const data = await response.json();
      if (data.url) window.location.href = data.url;
      else toast.error("Erro ao abrir portal de assinatura.");
    } catch {
      toast.error("Erro ao abrir portal de assinatura.");
    }
  };

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  const manageLabel =
    plan.planStatus === "free"     ? "Assinar Plano"           :
    plan.planStatus === "past_due" ? "Regularizar Pagamento"   :
                                     "Gerenciar Assinatura";

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-white/10 transition-all">
          <Avatar className="w-8 h-8">
            <AvatarFallback className="text-xs font-semibold gradient-primary text-primary-foreground">
              {initials}
            </AvatarFallback>
          </Avatar>
          <div className="hidden sm:flex flex-col items-start leading-tight">
            <span className="text-xs font-medium text-foreground max-w-[130px] truncate">{userEmail}</span>
            <span className="text-[10px] text-muted-foreground">{plan.planName}</span>
          </div>
          <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
        </button>
      </PopoverTrigger>

      <PopoverContent align="end" className="w-64 p-0 bg-card border-border/50 backdrop-blur-xl">
        {/* Cabeçalho */}
        <div className="p-4 border-b border-border/30">
          <p className="text-sm font-semibold text-foreground truncate">{userEmail}</p>
          <p className="text-xs text-muted-foreground mt-0.5">Conta ativa</p>
        </div>

        {/* Assinatura */}
        <div className="p-4 border-b border-border/30 space-y-2">
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Assinatura</p>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Plano</span>
            <span className={`text-xs font-semibold ${plan.planStatus === "past_due" ? "text-destructive" : "text-primary"}`}>
              {plan.planName}{plan.planStatus === "past_due" && " ⚠"}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Saldo</span>
            <span className="text-xs font-semibold text-foreground">
              {plan.pageBalance} / {plan.pageLimit} páginas
            </span>
          </div>
        </div>

        {/* Ações */}
        <div className="p-2">
          <button
            onClick={handleManageSubscription}
            className="flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-secondary/60 transition-colors w-full text-left"
          >
            <CreditCard className="w-4 h-4 text-muted-foreground" />
            <span className="text-sm text-foreground">{manageLabel}</span>
          </button>
          <Link
            to="/termos"
            className="flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-secondary/60 transition-colors w-full"
          >
            <Settings className="w-4 h-4 text-muted-foreground" />
            <span className="text-sm text-foreground">Termos de Uso</span>
          </Link>
          <div className="border-t border-border/30 mt-1 pt-1">
            <button
              onClick={handleLogout}
              className="flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-destructive/10 transition-colors w-full text-left"
            >
              <LogOut className="w-4 h-4 text-destructive" />
              <span className="text-sm text-destructive">Sair</span>
            </button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
};

// ─────────────────────────────────────────────────────────────
// Dados estáticos
// ─────────────────────────────────────────────────────────────
const features = [
  { icon: FileText, title: "Extração Inteligente", desc: "IA avançada para extrair dados de cartões ponto automaticamente." },
  { icon: Zap,      title: "Processamento Rápido", desc: "Resultados em segundos, não horas. Economize tempo valioso."      },
  { icon: Shield,   title: "Dados Seguros",         desc: "Seus documentos são processados com criptografia de ponta."       },
];

const REASON_MESSAGES: Record<string, string> = {
  past_due:       "Seu pagamento está pendente. Selecione um plano para regularizar e continuar usando o sistema.",
  free_exhausted: "Você utilizou todas as suas 50 páginas grátis. Assine um plano para continuar.",
  no_plan:        "Escolha um plano para acessar o sistema.",
};

interface LandingPageProps {
  /** Quando true (rota /planos), faz scroll automático para #pricing */
  scrollToPricing?: boolean;
}

// ─────────────────────────────────────────────────────────────
// Componente principal
// ─────────────────────────────────────────────────────────────
const LandingPage = ({ scrollToPricing }: LandingPageProps) => {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const { plan } = useUserPlan();
  const [searchParams] = useSearchParams();

  const hasActivePlan    = ACTIVE_PLANS.includes(plan.planStatus);
  const isFreeWithBalance = plan.planStatus === "free" && plan.pageBalance > 0;
  const canAccessApp     = hasActivePlan || isFreeWithBalance;

  const reason        = searchParams.get("reason") ?? "";
  const reasonMessage = REASON_MESSAGES[reason] ?? "";

  // Scroll automático para #pricing quando vindo de /planos
  useEffect(() => {
    if (scrollToPricing) {
      const t = setTimeout(() => {
        document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" });
      }, 300);
      return () => clearTimeout(t);
    }
  }, [scrollToPricing]);

  // Monta os planos para a seção de preços
  const plans = [
    {
      id: "free", name: "Free Trial", price: "Grátis",
      pages: "50 páginas", pricePerPage: null, extra: null,
      highlight: false, badge: "Bônus de cadastro",
      stripePriceId: null,
    },
    {
      id: "basic", name: "Básico", price: "R$ 179,90",
      pages: "200 páginas/mês", pricePerPage: "R$ 0,90 por página", extra: "R$ 1,00 por página extra",
      highlight: false, badge: null,
      stripePriceId: import.meta.env.VITE_STRIPE_PRICE_ID_BASICO,
    },
    {
      id: "standard", name: "Padrão", price: "R$ 349,90",
      pages: "500 páginas/mês", pricePerPage: "R$ 0,70 por página", extra: "R$ 0,85 por página extra",
      highlight: true, badge: null,
      stripePriceId: import.meta.env.VITE_STRIPE_PRICE_ID_PADRAO,
    },
    {
      id: "premium", name: "Premium", price: "R$ 824,90",
      pages: "1.500 páginas/mês", pricePerPage: "R$ 0,55 por página", extra: "R$ 0,70 por página extra",
      highlight: false, badge: null,
      stripePriceId: import.meta.env.VITE_STRIPE_PRICE_ID_PREMIUM,
    },
  ];

  const handleSelectPaidPlan = async (priceId: string | null | undefined) => {
    if (!priceId) return;
    if (!isAuthenticated) { window.location.href = "/cadastro"; return; }
    try {
      const { url } = await api.createCheckoutSession(priceId);
      window.location.href = url;
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Erro ao iniciar checkout.");
    }
  };

  // ── Helper: botão do card Free Trial muda conforme estado ──────────────
  const FreePlanButton = () => {
    if (!isAuthenticated) {
      // Não logado → convida para cadastro
      return (
        <Link to="/cadastro" className="block w-full">
          <button className="w-full py-2.5 rounded-lg text-sm font-semibold border border-primary/40 text-primary hover:bg-primary/10 transition-colors">
            Começar grátis
          </button>
        </Link>
      );
    }
    if (isFreeWithBalance) {
      // Logado com saldo → acessa o sistema
      return (
        <Link to="/app" className="block w-full">
          <button className="w-full py-2.5 rounded-lg text-sm font-semibold gradient-primary text-primary-foreground hover:shadow-lg transition-all">
            Acessar Sistema
          </button>
        </Link>
      );
    }
    // Logado sem saldo (free esgotado ou plano pago) → ainda tem free mas já usou
    // Mostra botão desabilitado com texto informativo
    return (
      <button
        disabled
        className="w-full py-2.5 rounded-lg text-sm font-semibold border border-border/30 text-muted-foreground cursor-not-allowed opacity-50"
        title="Você já utilizou o período gratuito"
      >
        Já utilizado
      </button>
    );
  };

  return (
    <div className="min-h-screen gradient-bg">

      {/* ══════════════════════════════════════════════════════
          HEADER
          Não logado:  [Planos]  [Login]  [Cadastro]
          Logado c/ acesso: [Ver Planos]  [Avatar ▾]
          Logado s/ acesso: [Ver Planos]  [Avatar ▾]
      ══════════════════════════════════════════════════════ */}
      <header className="sticky top-0 z-50 bg-background/60 backdrop-blur-xl border-b border-border/30">
        <div className="container mx-auto flex items-center justify-between py-4 px-6">
          <h1 className="text-xl font-bold text-foreground">Sistema Ponto</h1>

          <nav className="flex items-center gap-3">
            {/* Âncora para seção de planos — sempre visível */}
            <a
              href="#pricing"
              className="text-muted-foreground hover:text-foreground transition-colors text-sm"
            >
              Ver Planos
            </a>

            {!authLoading && (
              <>
                {isAuthenticated ? (
                  /* ── Logado: mostra botão de acesso + avatar ─────────── */
                  <>
                    {canAccessApp && (
                      <Link
                        to="/app"
                        className="gradient-primary text-primary-foreground px-4 py-2 rounded-lg text-sm font-semibold transition-all hover:shadow-[0_0_20px_rgba(74,158,255,0.3)]"
                      >
                        Acessar Sistema
                      </Link>
                    )}
                    {/* Avatar com popover — mesmo estilo do AppHeader */}
                    <LandingUserMenu />
                  </>
                ) : (
                  /* ── Não logado: Login + Cadastro ───────────────────── */
                  <>
                    <Link
                      to="/login"
                      className="text-muted-foreground hover:text-foreground transition-colors text-sm"
                    >
                      Login
                    </Link>
                    <Link
                      to="/cadastro"
                      className="gradient-primary text-primary-foreground px-5 py-2 rounded-lg text-sm font-semibold transition-all hover:shadow-[0_0_20px_rgba(74,158,255,0.3)]"
                    >
                      Cadastro
                    </Link>
                  </>
                )}
              </>
            )}
          </nav>
        </div>
      </header>

      {/* Banner contextual (past_due / free esgotado) */}
      {isAuthenticated && reasonMessage && (
        <div className="bg-amber-500/10 border-b border-amber-500/30 py-3 px-6 text-center">
          <p className="text-sm text-amber-600 dark:text-amber-400">{reasonMessage}</p>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════
          HERO
      ══════════════════════════════════════════════════════ */}
      <section className="relative py-32 px-6 overflow-hidden">
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
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
              Economize horas na extração de dados de cartões ponto. Nossa IA processa
              seus PDFs e entrega resultados precisos em segundos.
            </p>

            {/* CTA do hero — adapta conforme estado */}
            {isAuthenticated ? (
              canAccessApp ? (
                <Link
                  to="/app"
                  className="inline-flex items-center gap-2 gradient-primary text-primary-foreground px-8 py-4 rounded-xl font-bold text-base hover:shadow-[0_0_30px_rgba(74,158,255,0.4)] transition-all"
                >
                  Acessar o Sistema <ArrowRight className="w-5 h-5" />
                </Link>
              ) : (
                <a
                  href="#pricing"
                  className="inline-flex items-center gap-2 gradient-primary text-primary-foreground px-8 py-4 rounded-xl font-bold text-base hover:shadow-[0_0_30px_rgba(74,158,255,0.4)] transition-all"
                >
                  Ver Planos <ArrowRight className="w-5 h-5" />
                </a>
              )
            ) : (
              <Link
                to="/cadastro"
                className="inline-flex items-center gap-2 gradient-primary text-primary-foreground px-8 py-4 rounded-xl font-bold text-base hover:shadow-[0_0_30px_rgba(74,158,255,0.4)] transition-all"
              >
                Cadastre-se e ganhe 50 páginas grátis <ArrowRight className="w-5 h-5" />
              </Link>
            )}
          </motion.div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════
          FEATURES
      ══════════════════════════════════════════════════════ */}
      <section className="py-20 px-6">
        <div className="container mx-auto">
          <motion.h3
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-3xl font-bold text-center text-foreground mb-12"
          >
            Por que escolher o Sistema Ponto?
          </motion.h3>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {features.map((f, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                className="glass-card p-8 text-center"
              >
                <div className="w-14 h-14 gradient-primary rounded-2xl flex items-center justify-center mx-auto mb-5">
                  <f.icon className="w-7 h-7 text-primary-foreground" />
                </div>
                <h4 className="text-lg font-bold text-foreground mb-3">{f.title}</h4>
                <p className="text-muted-foreground text-sm leading-relaxed">{f.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════
          PRICING  —  id="pricing" obrigatório para âncoras
      ══════════════════════════════════════════════════════ */}
      <section id="pricing" className="py-20 px-6">
        <div className="container mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center mb-12"
          >
            <h3 className="text-3xl font-bold text-foreground mb-4">Planos e Preços</h3>
            <p className="text-muted-foreground max-w-xl mx-auto">
              Comece grátis e escale conforme sua necessidade.
            </p>
          </motion.div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 max-w-5xl mx-auto">
            {plans.map((p, i) => (
              <motion.div
                key={p.id}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.08 }}
                className={`glass-card p-6 flex flex-col relative ${
                  p.highlight ? "border-primary/50 shadow-[0_0_30px_rgba(74,158,255,0.15)]" : ""
                }`}
              >
                {p.highlight && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 gradient-primary rounded-full text-xs font-bold text-primary-foreground whitespace-nowrap">
                    Mais popular
                  </div>
                )}
                {p.badge && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-success/20 border border-success/30 rounded-full text-xs font-medium text-success whitespace-nowrap">
                    {p.badge}
                  </div>
                )}

                <h4 className="text-lg font-bold text-foreground mb-1">{p.name}</h4>
                <div className="text-3xl font-extrabold text-foreground mb-1">{p.price}</div>
                {p.pricePerPage && (
                  <p className="text-xs text-muted-foreground mb-3">{p.pricePerPage}</p>
                )}

                <ul className="flex-1 space-y-2 mb-6 mt-2">
                  <li className="text-sm text-muted-foreground flex items-center gap-2">
                    <span className="text-success">✓</span> {p.pages}
                  </li>
                  {p.extra && (
                    <li className="text-sm text-muted-foreground flex items-center gap-2">
                      <span className="text-success">✓</span> {p.extra}
                    </li>
                  )}
                </ul>

                {/* Botão: Free Trial tem lógica especial, os demais vão para checkout */}
                {p.id === "free" ? (
                  <FreePlanButton />
                ) : (
                  <button
                    onClick={() => handleSelectPaidPlan(p.stripePriceId)}
                    className={`w-full py-2.5 rounded-lg text-sm font-semibold transition-all ${
                      p.highlight
                        ? "gradient-primary text-primary-foreground hover:shadow-lg hover:shadow-primary/25"
                        : "border border-border hover:bg-secondary/60 text-foreground"
                    }`}
                  >
                    Assinar
                  </button>
                )}
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-6 border-t border-border/30 text-center">
        <p className="text-muted-foreground text-sm">
          © {new Date().getFullYear()} Sistema Ponto.{" "}
          <Link to="/termos" className="hover:text-foreground transition-colors">
            Termos de Uso
          </Link>
        </p>
      </footer>
    </div>
  );
};

export default LandingPage;
