// frontend/src/pages/MaintenancePage.tsx
//
// Tela fullscreen mostrada para usuários comuns durante manutenção.
// Auto-refresh a cada 30s para detectar quando voltou.

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Wrench, RefreshCw, Clock, MessageCircle, Download } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useMaintenance } from "@/hooks/useMaintenance";

const WHATSAPP_URL =
  "https://wa.me/5554999427282?text=Olá! Tenho dúvidas durante a manutenção do Sistema Ponto.";

const MaintenancePage = () => {
  const { status, refetch, isLoading } = useMaintenance();
  const navigate = useNavigate();
  const [now, setNow] = useState(new Date());
  const [refreshing, setRefreshing] = useState(false);

  // Atualiza tempo a cada segundo
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // Quando manutenção termina, redireciona pra /app
  useEffect(() => {
    if (!isLoading && !status.active) {
      navigate("/app", { replace: true });
    }
  }, [status.active, isLoading, navigate]);

  const handleManualRefresh = async () => {
    setRefreshing(true);
    await refetch();
    setTimeout(() => setRefreshing(false), 800);
  };

  // Cálculo de tempo restante
  const endsAt = status.ends_at ? new Date(status.ends_at) : null;
  const startsAt = status.starts_at ? new Date(status.starts_at) : null;

  const remainingMs = endsAt ? Math.max(0, endsAt.getTime() - now.getTime()) : 0;
  const remainingHours = Math.floor(remainingMs / (1000 * 60 * 60));
  const remainingMinutes = Math.floor((remainingMs % (1000 * 60 * 60)) / (1000 * 60));

  const formatRemaining = () => {
    if (remainingMs <= 0) return "alguns instantes";
    if (remainingHours > 0) {
      return `${remainingHours}h ${remainingMinutes.toString().padStart(2, "0")}min`;
    }
    return `${remainingMinutes} minuto${remainingMinutes !== 1 ? "s" : ""}`;
  };

  const formatDate = (d: Date | null) => {
    if (!d) return "—";
    return d.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="min-h-screen gradient-bg flex items-center justify-center p-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-lg"
      >
        <div className="text-center">
          {/* Ícone com animação leve */}
          <motion.div
            animate={{ rotate: [0, -8, 8, -8, 0] }}
            transition={{ duration: 2.5, repeat: Infinity, repeatDelay: 1.5 }}
            className="w-24 h-24 rounded-3xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center mx-auto mb-6"
          >
            <Wrench className="w-12 h-12 text-amber-500" />
          </motion.div>

          <h1 className="text-3xl font-bold text-foreground mb-3">
            Sistema em manutenção
          </h1>

          <p className="text-base text-muted-foreground leading-relaxed mb-2 whitespace-pre-line">
            {status.message || "Estamos atualizando o sistema para você."}
          </p>

          {remainingMs > 0 && (
            <p className="text-sm text-muted-foreground mb-6">
              Voltamos em aproximadamente <strong className="text-foreground">{formatRemaining()}</strong>.
            </p>
          )}
        </div>

        {/* Card de info */}
        <div className="glass-card p-5 mb-5">
          <div className="space-y-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground flex items-center gap-2">
                <Clock className="w-4 h-4" />
                Início
              </span>
              <span className="text-foreground font-medium">
                {formatDate(startsAt)}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-muted-foreground flex items-center gap-2">
                <Clock className="w-4 h-4" />
                Previsão
              </span>
              <span className="text-foreground font-medium">
                {formatDate(endsAt)}
              </span>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-border/30">
              <span className="text-muted-foreground">Status</span>
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2 py-0.5 rounded bg-amber-500/15 text-amber-600 dark:text-amber-400">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                Em andamento
              </span>
            </div>
          </div>
        </div>

        {/* Auto-refresh + botão manual */}
        <div className="flex items-center justify-center gap-3 mb-5 text-sm text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
            Verificando automaticamente a cada 30s
          </span>
        </div>

        <button
          onClick={handleManualRefresh}
          disabled={refreshing}
          className="w-full gradient-primary text-primary-foreground font-semibold py-3 rounded-lg flex items-center justify-center gap-2 hover:opacity-90 transition disabled:opacity-60 mb-3"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} />
          {refreshing ? "Verificando..." : "Tentar agora"}
        </button>

        {/* Atalho para downloads */}
        <Link
          to="/app"
          className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg border border-border/50 text-sm text-foreground hover:bg-secondary/30 transition mb-3"
        >
          <Download className="w-4 h-4 text-emerald-500" />
          Tem trabalho pronto? Downloads continuam liberados
        </Link>

        {/* Suporte */}
        <a
          href={WHATSAPP_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="w-full flex items-center justify-center gap-2 py-2.5 text-sm text-muted-foreground hover:text-emerald-500 transition"
        >
          <MessageCircle className="w-4 h-4" />
          Dúvidas? Fale conosco no WhatsApp
        </a>
      </motion.div>
    </div>
  );
};

export default MaintenancePage;
