import { Link, useNavigate } from "react-router-dom";
import { LogOut, CreditCard, Settings, ChevronDown, Headset } from "lucide-react";
import StatusWidget from "@/components/StatusWidget";
import { useUserPlan } from "@/hooks/useUserPlan";
import { useAuth } from "@/contexts/AuthContext";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { api } from "@/lib/api";
import { toast } from "sonner";
const WHATSAPP_URL = "https://wa.me/5511999999999?text=Olá! Preciso de suporte no Sistema Ponto.";

const STRIPE_PRICE_IDS: Record<string, string> = {
  basic: import.meta.env.VITE_STRIPE_PRICE_ID_BASICO || "",
  standard: import.meta.env.VITE_STRIPE_PRICE_ID_PADRAO || "",
  premium: import.meta.env.VITE_STRIPE_PRICE_ID_PREMIUM || "",
};

const AppHeader = () => {
  const { plan, isLoading: planLoading } = useUserPlan();
  const { logout } = useAuth();
  const navigate = useNavigate();

  const userEmail = plan.email || "usuario@email.com";
  const initials = userEmail.substring(0, 2).toUpperCase();

  const handleManageSubscription = async () => {
    if (plan.planStatus === "free") {
      // Redirect to pricing
      navigate("/#priceing");
      return;
    }
    try {
      const token = localStorage.getItem("access_token");
      const response = await fetch("/api/create-portal-session", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });
      const data = await response.json();
      if (data.url) {
        window.location.href = data.url;
      } else {
        toast.error("Erro ao abrir portal.");
      }
    } catch {
      toast.error("Erro ao abrir portal de assinatura.");
    }
  };


  return (
    <header className="flex items-center justify-between px-6 py-3 bg-background/80 backdrop-blur-xl border-b border-border/30 shrink-0">
      <Link to="/app" className="text-lg font-bold text-foreground hover:text-primary transition-colors">
        Sistema Ponto
      </Link>
      <div className="flex items-center gap-4">
        <StatusWidget
          planName={plan.planName}
          pageBalance={plan.pageBalance}
          pageLimit={plan.pageLimit}
          extraPages={plan.extraPages}
          isLoading={planLoading}
        />

        <a
          href={WHATSAPP_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center w-9 h-9 rounded-lg hover:bg-secondary/60 transition-all text-muted-foreground hover:text-success"
          title="Suporte via WhatsApp"
        >
          <Headset className="w-5 h-5" />
        </a>

        <Popover>
          <PopoverTrigger asChild>
            <button className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-secondary/60 transition-all">
              <Avatar className="w-8 h-8 border border-border/50">
                <AvatarImage src={`https://api.dicebear.com/7.x/initials/svg?seed=${userEmail}&backgroundColor=0f3460&textColor=4a9eff`} />
                <AvatarFallback className="bg-secondary text-primary text-xs font-semibold">
                  {initials}
                </AvatarFallback>
              </Avatar>
              <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
            </button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-72 p-0 bg-card border-border/50 backdrop-blur-xl">
            <div className="p-4 border-b border-border/30">
              <p className="text-sm font-semibold text-foreground">{userEmail}</p>
              <p className="text-xs text-muted-foreground mt-0.5">Conta ativa</p>
            </div>

            <div className="p-4 border-b border-border/30 space-y-3">
              <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Assinatura</h4>
              <div className="flex items-center justify-between">
                <span className="text-sm text-foreground">Plano</span>
                <span className="text-sm font-semibold text-primary">{plan.planName}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-foreground">Saldo</span>
                <span className="text-sm font-semibold text-foreground">{plan.pageBalance} / {plan.pageLimit} páginas</span>
              </div>
              {plan.extraPages > 0 && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-foreground">Extras consumidas</span>
                  <span className="text-sm font-semibold text-warning">{plan.extraPages} páginas</span>
                </div>
              )}
            </div>

            <div className="p-2">
              <button
                onClick={handleManageSubscription}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-foreground hover:bg-secondary/60 transition-all w-full text-left"
              >
                <CreditCard className="w-4 h-4 text-muted-foreground" />
                Gerenciar Assinatura
              </button>
              <Link
                to="/termos"
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-foreground hover:bg-secondary/60 transition-all w-full"
              >
                <Settings className="w-4 h-4 text-muted-foreground" />
                Termos de Uso
              </Link>
              <button
                onClick={logout}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-destructive hover:bg-destructive/10 transition-all w-full text-left"
              >
                <LogOut className="w-4 h-4" />
                Sair
              </button>
            </div>
          </PopoverContent>
        </Popover>
      </div>
    </header>
  );
};

export default AppHeader;
