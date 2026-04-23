// frontend/src/pages/PromocoesPage.tsx
//
// Página /promocoes — vista completa de todas as promoções ativas.
// Card de indicação + lista de promoções dinâmicas em formato full.

import { useEffect } from "react";
import { motion } from "framer-motion";
import { ArrowLeft, Gift, Loader2, PartyPopper } from "lucide-react";
import { Link } from "react-router-dom";
import AppHeader from "@/components/AppHeader";
import ReferralCard from "@/components/ReferralCard";
import PromotionCard from "@/components/PromotionCard";
import { usePromotions, trackPromotionEvent } from "@/hooks/usePromotions";

const PromocoesPage = () => {
  const { promotions, isLoading } = usePromotions();

  // Track impressões ao entrar na página
  useEffect(() => {
    if (!isLoading && promotions.length > 0) {
      promotions.forEach((p) => {
        trackPromotionEvent(p.id, "impression");
      });
    }
  }, [isLoading, promotions]);

  return (
    <div className="min-h-screen gradient-bg">
      <AppHeader />

      <main className="container mx-auto max-w-3xl px-6 py-8">
        <Link
          to="/app"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition mb-6"
        >
          <ArrowLeft className="w-4 h-4" />
          Voltar
        </Link>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
              <Gift className="w-5 h-5 text-primary" />
            </div>
            <h1 className="text-3xl font-bold text-foreground">
              Descontos e Promoções
            </h1>
          </div>
          <p className="text-muted-foreground">
            Todas as ofertas disponíveis agora no Sistema Ponto.
          </p>
        </motion.div>

        <div className="space-y-4">
          {/* Card permanente: Indicação */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
          >
            <ReferralCard variant="full" />
          </motion.div>

          {/* Cards dinâmicos */}
          {isLoading ? (
            <div className="glass-card p-10 flex items-center justify-center">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : promotions.length === 0 ? (
            <div className="glass-card p-10 text-center">
              <PartyPopper className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">
                No momento não há promoções ativas.
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Continue indicando amigos para economizar na mensalidade.
              </p>
            </div>
          ) : (
            promotions.map((p, i) => (
              <motion.div
                key={p.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05 + i * 0.05 }}
              >
                <PromotionCard promotion={p} variant="full" />
              </motion.div>
            ))
          )}
        </div>
      </main>
    </div>
  );
};

export default PromocoesPage;
