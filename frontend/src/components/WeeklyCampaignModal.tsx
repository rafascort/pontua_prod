// frontend/src/components/WeeklyCampaignModal.tsx
//
// Modal semanal — 1x por semana após login.
// Card de indicação (permanente, primeiro) + cards de promoções ativas (dinâmicos).

import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";
import ReferralCard from "./ReferralCard";
import PromotionCard from "./PromotionCard";
import { usePromotions, trackPromotionEvent } from "@/hooks/usePromotions";

interface Props {
  open: boolean;
  onClose: () => void;
}

const WeeklyCampaignModal = ({ open, onClose }: Props) => {
  const { promotions, isLoading } = usePromotions();

  // Registra impressão de cada promoção quando o modal abre
  useEffect(() => {
    if (open && !isLoading && promotions.length > 0) {
      promotions.forEach((p) => {
        trackPromotionEvent(p.id, "impression");
      });
    }
  }, [open, isLoading, promotions]);

  const promoLabel = promotions.length === 0
    ? "Programa de indicação"
    : `Programa de indicação · ${promotions.length} ${
        promotions.length === 1 ? "promoção ativa" : "promoções ativas"
      }`;

  const subtitle = promotions.length === 0
    ? "Indique amigos e ganhe desconto na mensalidade."
    : "Indique amigos e confira as promoções que estão acontecendo.";

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto"
          role="dialog"
          aria-modal="true"
          aria-labelledby="campaign-modal-title"
        >
          <motion.div
            initial={{ opacity: 0, y: 30, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
            onClick={(e) => e.stopPropagation()}
            className="bg-card rounded-2xl border border-border/50 w-full max-w-xl my-8 overflow-hidden shadow-2xl"
          >
            {/* Header */}
            <div className="relative p-6 pb-4">
              <button
                onClick={onClose}
                aria-label="Fechar"
                className="absolute top-4 right-4 w-8 h-8 rounded-full flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/50 transition"
              >
                <X className="w-4 h-4" />
              </button>
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5">
                {promoLabel}
              </p>
              <h2
                id="campaign-modal-title"
                className="text-2xl font-bold text-foreground"
              >
                Economize na sua mensalidade
              </h2>
              <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>
            </div>

            {/* Cards */}
            <div className="px-6 pb-6 space-y-3">
              {/* Card permanente: Indicação */}
              <ReferralCard variant="modal" />

              {/* Cards dinâmicos: Promoções */}
              {promotions.map((p) => (
                <PromotionCard key={p.id} promotion={p} variant="modal" />
              ))}
            </div>

            {/* Footer */}
            <div className="px-6 py-3 border-t border-border/50 flex items-center justify-between">
              <p className="text-xs text-muted-foreground">
                Não será exibido novamente por 7 dias.
              </p>
              <button
                onClick={onClose}
                className="text-sm font-medium px-4 py-1.5 rounded-md border border-border/50 hover:bg-muted/50 transition"
              >
                Fechar
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default WeeklyCampaignModal;
