// frontend/src/components/AppHeader.tsx
import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { LogOut, CreditCard, ChevronDown, Headset, Settings, Users, Gift, Building, ShieldCheck } from "lucide-react";
import AnnouncementBlockingModal from "@/components/AnnouncementBlockingModal";
import AdminMaintenanceBanner from "@/components/AdminMaintenanceBanner";
import StatusWidget from "@/components/StatusWidget";
import { useUserPlan } from "@/hooks/useUserPlan";
import { useAuth } from "@/contexts/AuthContext";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { toast } from "sonner";
import { api } from "@/lib/api";
import PlanManagerModal from "@/components/PlanManagerModal";
import ScheduledChangeBanner from "@/components/ScheduledChangeBanner";


const WHATSAPP_URL =
  "https://wa.me/5554999427282?text=Ol%C3%A1! Preciso de suporte no Sistema Ponto.";

const ACTIVE_PLANS = ["basic", "standard", "premium"];

function jwtClaims(): any {
  try {
    const token = localStorage.getItem("access_token");
    if (!token) return {};
    return JSON.parse(atob(token.split(".")[1]));
  } catch { return {}; }
}

const AppHeader = () => {
  const { plan, isLoading: planLoading } = useUserPlan();
  const { logout } = useAuth();
  const navigate   = useNavigate();

  const claims  = jwtClaims();
  const orgId   = claims.organization_id;
  const orgRole = claims.org_role;
  const [orgName, setOrgName] = useState<string | null>(null);
  const [planModalOpen, setPlanModalOpen] = useState(false);
  const [subStatus, setSubStatus] = useState<{
    current_plan: string;
    scheduled_change: { plan: string; effective_date: number } | null;
  } | null>(null);

  const loadSubStatus = () => {
    if (!ACTIVE_PLANS.includes(plan.planStatus)) return;
    api.getSubscriptionStatus().then(setSubStatus).catch(() => {});
  };
  useEffect(() => { loadSubStatus(); /* eslint-disable-next-line */ }, [plan.planStatus]);

  useEffect(() => {
    if (!orgId) return;
    fetch("/api/org/me", {
      headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` },
    })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.organization?.name) setOrgName(d.organization.name); })
      .catch(() => {});
  }, [orgId]);

  const userEmail  = plan.email || "usuario@email.com";
  const initials   = userEmail.substring(0, 2).toUpperCase();
  const isPaidPlan = ACTIVE_PLANS.includes(plan.planStatus);
  const hasExtras  = plan.extraPages > 0;

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
      else toast.error("URL do portal nao retornada.");
    } catch {
      toast.error("Erro de conexao ao abrir portal de assinatura.");
    }
  };

  if (planLoading) {
    return (
      <header className="sticky top-0 z-40 bg-background/80 backdrop-blur-xl border-b border-border/30 h-14" />
    );
  }

  const manageLabel =
    plan.planStatus === "past_due" ? "Regularizar Pagamento" :
    !isPaidPlan                    ? "Assinar Plano"         :
                                     "Gerenciar Assinatura";

  return (
    <>
      {subStatus?.scheduled_change && (
        <ScheduledChangeBanner
          scheduledPlan={subStatus.scheduled_change.plan}
          effectiveDate={subStatus.scheduled_change.effective_date}
          onCancelled={loadSubStatus}
        />
      )}
      <header className="sticky top-0 z-40 bg-background/80 backdrop-blur-xl border-b border-border/30">
        <div className="container mx-auto flex items-center justify-between h-14 px-4 gap-3">

          <Link to="/app" className="text-base font-bold text-foreground hover:text-primary transition-colors shrink-0">
            Sistema Ponto
          </Link>

          {orgId ? (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary/10 border border-primary/20 text-primary text-xs">
              <ShieldCheck className="w-3.5 h-3.5 shrink-0" />
              <span className="font-medium max-w-[200px] truncate">
                via {orgName || "sua empresa"}
              </span>
              <span className="text-muted-foreground hidden sm:inline">uso ilimitado</span>
            </div>
          ) : (
            <StatusWidget
              planName={plan.planName}
              pageBalance={plan.pageBalance}
              pageLimit={plan.pageLimit}
              extraPages={plan.extraPages}
              planStatus={plan.planStatus}
              pageCount={plan.pageCount}
              isLoading={planLoading}
            />
          )}

          <div className="flex items-center gap-2 shrink-0">

            {orgId && orgRole === "admin" && (
              <Link
                to="/empresa"
                className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border/50 text-muted-foreground hover:text-foreground hover:border-border text-xs transition-all"
              >
                <Building className="w-3.5 h-3.5" /> Empresa
              </Link>
            )}

            <Popover>
              <PopoverTrigger asChild>
                <button className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-secondary/60 transition-colors">
                  <Avatar className="w-8 h-8">
                    <AvatarFallback className="text-xs font-semibold gradient-primary text-primary-foreground">
                      {initials}
                    </AvatarFallback>
                  </Avatar>
                  <div className="hidden sm:flex flex-col items-start leading-tight">
                    <span className="text-xs font-medium text-foreground max-w-[140px] truncate">{userEmail}</span>
                    <span className={`text-[10px] ${plan.planStatus === "past_due" && !orgId ? "text-destructive" : "text-muted-foreground"}`}>
                      {orgId
                        ? (orgRole === "admin" ? "Admin da empresa" : "Funcionario")
                        : `${plan.planName}${plan.planStatus === "past_due" ? " !" : ""}`}
                    </span>
                  </div>
                  <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
                </button>
              </PopoverTrigger>

              <PopoverContent align="end" className="w-64 p-0 bg-card border-border/50 backdrop-blur-xl">

                <div className="p-4 border-b border-border/30">
                  <p className="text-sm font-medium text-foreground truncate">{userEmail}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {orgId ? ("via " + (orgName || "sua empresa")) : "Conta ativa"}
                  </p>
                </div>

                {orgId ? (
                  <div className="p-4 border-b border-border/30 space-y-2">
                    <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Acesso pela empresa</p>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Funcao</span>
                      <span className="text-xs font-semibold text-primary">
                        {orgRole === "admin" ? "Administrador" : "Funcionario"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Paginas</span>
                      <span className="text-xs font-semibold text-foreground">Uso ilimitado</span>
                    </div>
                    <p className="text-[10px] text-muted-foreground pt-1">
                      A empresa paga pelo uso ao final do mes.
                    </p>
                  </div>
                ) : (
                  <div className="p-4 border-b border-border/30 space-y-2">
                    <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">Assinatura</p>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Plano</span>
                      <span className={`text-xs font-semibold ${plan.planStatus === "past_due" ? "text-destructive" : "text-primary"}`}>
                        {plan.planName}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">Paginas incluidas</span>
                      <span className="text-xs font-semibold text-foreground">
                        {plan.pageBalance} / {plan.pageLimit} restantes
                      </span>
                    </div>
                    {hasExtras && isPaidPlan && (
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-muted-foreground">Paginas extras</span>
                        <span className="text-xs font-semibold text-amber-400">
                          +{plan.extraPages.toLocaleString("pt-BR")} cobraveis
                        </span>
                      </div>
                    )}
                    {isPaidPlan && plan.pageBalance <= 0 && !hasExtras && (
                      <p className="text-[10px] text-amber-400 pt-1">
                        Limite incluido atingido. Proximas paginas serao cobradas a parte.
                      </p>
                    )}
                    {isPaidPlan && hasExtras && (
                      <p className="text-[10px] text-muted-foreground pt-1">
                        Extras cobrados no proximo ciclo de faturamento.
                      </p>
                    )}
                  </div>
                )}

                {!orgId && (
                  <div className="p-2 border-b border-border/30">
                    <Link
                      to="/indicacoes"
                      className="flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-secondary/60 transition-colors w-full"
                    >
                      <Users className="w-4 h-4 text-emerald-500" />
                      <div className="flex-1 text-left">
                        <div className="text-sm text-foreground">Minhas Indicacoes</div>
                        <div className="text-[10px] text-muted-foreground">Ganhe ate 40% OFF</div>
                      </div>
                    </Link>
                    <Link
                      to="/promocoes"
                      className="flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-secondary/60 transition-colors w-full"
                    >
                      <Gift className="w-4 h-4 text-indigo-500" />
                      <div className="flex-1 text-left">
                        <div className="text-sm text-foreground">Descontos e Promocoes</div>
                        <div className="text-[10px] text-muted-foreground">Ofertas ativas agora</div>
                      </div>
                    </Link>
                  </div>
                )}

                <div className="p-2">
                  {!orgId && (
                    <button
                      onClick={() => { isPaidPlan ? setPlanModalOpen(true) : handleManageSubscription(); }}
                      className="flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-secondary/60 transition-colors w-full text-left"
                    >
                      <CreditCard className="w-4 h-4 text-muted-foreground" />
                      <span className="text-sm text-foreground">{manageLabel}</span>
                    </button>
                  )}
                  {!orgId && isPaidPlan && (
                    <button
                      onClick={handleManageSubscription}
                      className="flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-secondary/60 transition-colors w-full text-left"
                    >
                      <CreditCard className="w-4 h-4 text-muted-foreground opacity-60" />
                      <span className="text-xs text-muted-foreground">Forma de pagamento / faturas</span>
                    </button>
                  )}

                  {orgId && orgRole === "admin" && (
                    <Link
                      to="/empresa"
                      className="flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-secondary/60 transition-colors w-full"
                    >
                      <Building className="w-4 h-4 text-muted-foreground" />
                      <span className="text-sm text-foreground">Area da empresa</span>
                    </Link>
                  )}

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

        </div>
      </header>

      <PlanManagerModal
        open={planModalOpen}
        onOpenChange={setPlanModalOpen}
        currentPlan={subStatus?.current_plan ?? plan.planStatus}
        scheduledPlan={subStatus?.scheduled_change?.plan ?? null}
        onChanged={loadSubStatus}
      />

      <AdminMaintenanceBanner />
      <AnnouncementBlockingModal />
    </>
  );
};

export default AppHeader;
