// frontend/src/components/AppHeader.tsx
import { useNavigate, Link } from "react-router-dom";
import { LogOut, CreditCard, ChevronDown, Headset, Settings, Users, Gift } from "lucide-react";
import StatusWidget from "@/components/StatusWidget";
import { useUserPlan } from "@/hooks/useUserPlan";
import { useAuth } from "@/contexts/AuthContext";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { toast } from "sonner";

const WHATSAPP_URL =
  "https://wa.me/5554999427282?text=Olá! Preciso de suporte no Sistema Ponto.";

const ACTIVE_PLANS = ["basic", "standard", "premium"];

const AppHeader = () => {
  const { plan, isLoading: planLoading } = useUserPlan();
  const { logout } = useAuth();
  const navigate   = useNavigate();

  const userEmail   = plan.email || "usuario@email.com";
  const initials    = userEmail.substring(0, 2).toUpperCase();
  const isPaidPlan  = ACTIVE_PLANS.includes(plan.planStatus);
  const hasExtras   = plan.extraPages > 0;

  const handleManageSubscription = async () => {
    if (!isPaidPlan) {
      window.location.href = `/#pricing?reason=${plan.planStatus === "past_due" ? "past_due" : "free_exhausted"}`;
      return;
    }
    try {
      const token    = localStorage.getItem("access_token");
      const response = await fetch("/api/create-portal-session", {
        method:  "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      });
      if (!response.ok) { toast.error("Erro ao abrir portal de assinatura."); return; }
      const data = await response.json();
      if (data.url) window.location.href = data.url;
      else toast.error("URL do portal não retornada.");
    } catch {
      toast.error("Erro de conexão ao abrir portal de assinatura.");
    }
  };

  if (planLoading) {
    return (
      <header className="sticky top-0 z-40 bg-background/80 backdrop-blur-xl border-b border-border/30 h-14" />
    );
  }

  const manageLabel =
    plan.planStatus === "past_due" ? "Regularizar Pagamento"  :
    !isPaidPlan                    ? "Assinar Plano"          :
                                     "Gerenciar Assinatura";

  return (
    <header className="sticky top-0 z-40 bg-background/80 backdrop-blur-xl border-b border-border/30">
      <div className="container mx-auto flex items-center justify-between h-14 px-4 gap-3">

        {/* Logo */}
        <Link to="/app" className="text-base font-bold text-foreground hover:text-primary transition-colors shrink-0">
          Sistema Ponto
        </Link>

        {/* Widget de saldo — centro */}
        <StatusWidget
          planName={plan.planName}
          pageBalance={plan.pageBalance}
          pageLimit={plan.pageLimit}
          extraPages={plan.extraPages}
          planStatus={plan.planStatus}
          pageCount={plan.pageCount}
          isLoading={planLoading}
        />

        {/* Menu do usuário */}
        <Popover>
          <PopoverTrigger asChild>
            <button className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-secondary/60 transition-colors shrink-0">
              <Avatar className="w-8 h-8">
                <AvatarFallback className="text-xs font-semibold gradient-primary text-primary-foreground">
                  {initials}
                </AvatarFallback>
              </Avatar>
              <div className="hidden sm:flex flex-col items-start leading-tight">
                <span className="text-xs font-medium text-foreground max-w-[140px] truncate">{userEmail}</span>
                <span className={`text-[10px] ${plan.planStatus === "past_due" ? "text-destructive" : "text-muted-foreground"}`}>
                  {plan.planName}{plan.planStatus === "past_due" && " ⚠"}
                </span>
              </div>
              <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
            </button>
          </PopoverTrigger>

          <PopoverContent align="end" className="w-64 p-0 bg-card border-border/50 backdrop-blur-xl">
            {/* Cabeçalho */}
            <div className="p-4 border-b border-border/30">
              <p className="text-sm font-medium text-foreground truncate">{userEmail}</p>
              <p className="text-xs text-muted-foreground mt-0.5">Conta ativa</p>
            </div>

            {/* Assinatura */}
            <div className="p-4 border-b border-border/30 space-y-2">
              <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Assinatura</p>

              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Plano</span>
                <span className={`text-xs font-semibold ${plan.planStatus === "past_due" ? "text-destructive" : "text-primary"}`}>
                  {plan.planName}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">Páginas incluídas</span>
                <span className="text-xs font-semibold text-foreground">
                  {plan.pageBalance} / {plan.pageLimit} restantes
                </span>
              </div>

              {/* Extras — só para planos pagos, com tom neutro */}
              {hasExtras && isPaidPlan && (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted-foreground">Páginas extras</span>
                  <span className="text-xs font-semibold text-amber-400">
                    +{plan.extraPages.toLocaleString("pt-BR")} cobráveis
                  </span>
                </div>
              )}

              {/* Aviso suave quando limite atingido em plano pago */}
              {isPaidPlan && plan.pageBalance <= 0 && !hasExtras && (
                <p className="text-[10px] text-amber-400 pt-1">
                  Limite incluído atingido. Próximas páginas serão cobradas à parte.
                </p>
              )}
              {isPaidPlan && hasExtras && (
                <p className="text-[10px] text-muted-foreground pt-1">
                  Extras cobrados no próximo ciclo de faturamento.
                </p>
              )}
            </div>

            {/* ── NOVOS: Indicações + Promoções ────────────────────── */}
            <div className="p-2 border-b border-border/30">
              <Link
                to="/indicacoes"
                className="flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-secondary/60 transition-colors w-full"
              >
                <Users className="w-4 h-4 text-emerald-500" />
                <div className="flex-1 text-left">
                  <div className="text-sm text-foreground">Minhas Indicações</div>
                  <div className="text-[10px] text-muted-foreground">Ganhe até 40% OFF</div>
                </div>
              </Link>

              <Link
                to="/promocoes"
                className="flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-secondary/60 transition-colors w-full"
              >
                <Gift className="w-4 h-4 text-indigo-500" />
                <div className="flex-1 text-left">
                  <div className="text-sm text-foreground">Descontos e Promoções</div>
                  <div className="text-[10px] text-muted-foreground">Ofertas ativas agora</div>
                </div>
              </Link>
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

              <a
                href={WHATSAPP_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-secondary/60 transition-colors w-full"
              >
                <Headset className="w-4 h-4 text-muted-foreground" />
                <span className="text-sm text-foreground">Suporte</span>
              </a>

              <Link
                to="/termos"
                className="flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-secondary/60 transition-colors w-full"
              >
                <Settings className="w-4 h-4 text-muted-foreground" />
                <span className="text-sm text-foreground">Termos de Uso</span>
              </Link>

              <div className="border-t border-border/30 mt-1 pt-1">
                <button
                  onClick={() => { logout(); navigate("/"); }}
                  className="flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-destructive/10 transition-colors w-full text-left"
                >
                  <LogOut className="w-4 h-4 text-destructive" />
                  <span className="text-sm text-destructive">Sair</span>
                </button>
              </div>
            </div>
          </PopoverContent>
        </Popover>

      </div>
    </header>
  );
};

export default AppHeader;
