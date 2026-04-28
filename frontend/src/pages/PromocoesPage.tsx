// frontend/src/pages/PromocoesPage.tsx
//
// Página /promocoes — vista completa de todas as promoções dinâmicas.
// O programa de indicação tem página própria (/indicacoes) e não aparece aqui.

import { useEffect } from "react";
import { motion } from "framer-motion";
import { ArrowLeft, Gift, Loader2, PartyPopper, Users } from "lucide-react";
import { Link } from "react-router-dom";
import AppHeader from "@/components/AppHeader";
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
            Ofertas e campanhas ativas do Sistema Ponto.
          </p>
        </motion.div>

        <div className="space-y-4">
          {isLoading ? (
            <div className="glass-card p-10 flex items-center justify-center">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : promotions.length === 0 ? (
            <div className="glass-card p-10 text-center">
              <PartyPopper className="w-10 h-10 text-muted-foreground/40 mx-auto mb-3" />
              <p className="text-sm text-muted-foreground mb-1">
                No momento não há promoções ativas.
              </p>
              <p className="text-xs text-muted-foreground">
                Quando lançarmos uma nova oferta, ela aparece por aqui.
              </p>

              {/* Atalho discreto para Indicações — só na tela vazia */}
              <Link
                to="/indicacoes"
                className="inline-flex items-center gap-1.5 mt-5 px-4 py-2 rounded-md text-xs font-medium bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition"
              >
                <Users className="w-3.5 h-3.5" />
                Conheça nosso programa de indicação
              </Link>
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
