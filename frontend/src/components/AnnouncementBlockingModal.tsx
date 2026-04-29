// frontend/src/components/AnnouncementBlockingModal.tsx
//
// Modal bloqueante que aparece após login com avisos pendentes.
// Múltiplos avisos viram uma fila — usuário precisa confirmar cada um com "Entendi".

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Info, AlertTriangle, AlertOctagon, Sparkles, Loader2,
} from "lucide-react";
import {
  useAnnouncements,
  acknowledgeAnnouncement,
  type AnnouncementSeverity,
} from "@/hooks/useAnnouncements";

const SEVERITY_CONFIG: Record<AnnouncementSeverity, {
  icon: typeof Info;
  iconColor: string;
  iconBg: string;
  badgeBg: string;
  badgeText: string;
  borderColor: string;
  badgeLabel: string;
}> = {
  info: {
    icon: Info,
    iconColor: "text-blue-500",
    iconBg: "bg-blue-500/15",
    badgeBg: "bg-blue-500/15",
    badgeText: "text-blue-600 dark:text-blue-400",
    borderColor: "border-blue-500/30",
    badgeLabel: "Informação",
  },
  warning: {
    icon: AlertTriangle,
    iconColor: "text-amber-500",
    iconBg: "bg-amber-500/15",
    badgeBg: "bg-amber-500/15",
    badgeText: "text-amber-600 dark:text-amber-400",
    borderColor: "border-amber-500/30",
    badgeLabel: "Aviso",
  },
  critical: {
    icon: AlertOctagon,
    iconColor: "text-red-500",
    iconBg: "bg-red-500/15",
    badgeBg: "bg-red-500/15",
    badgeText: "text-red-600 dark:text-red-400",
    borderColor: "border-red-500/30",
    badgeLabel: "Crítico",
  },
  news: {
    icon: Sparkles,
    iconColor: "text-emerald-500",
    iconBg: "bg-emerald-500/15",
    badgeBg: "bg-emerald-500/15",
    badgeText: "text-emerald-600 dark:text-emerald-400",
    borderColor: "border-emerald-500/30",
    badgeLabel: "Novidade",
  },
};

const AnnouncementBlockingModal = () => {
  const { announcements, refetch } = useAnnouncements();
  const [currentIndex, setCurrentIndex] = useState(0);
  const [confirming, setConfirming] = useState(false);

  // Reset index quando lista muda (novo aviso aparece via polling)
  useEffect(() => {
    setCurrentIndex(0);
  }, [announcements.length]);

  const total = announcements.length;
  const current = announcements[currentIndex];

  if (!current) return null;

  const config = SEVERITY_CONFIG[current.severity];
  const Icon = config.icon;

  const handleAcknowledge = async () => {
    if (confirming) return;
    setConfirming(true);

    const ok = await acknowledgeAnnouncement(current.id);

    if (!ok) {
      // Mesmo se falhou, tenta avançar — usuário não fica preso
      console.warn(`[AVISO] Falha ao registrar ack do aviso ${current.id}`);
    }

    // Se há mais avisos na fila, avança
    if (currentIndex < total - 1) {
      setCurrentIndex(currentIndex + 1);
      setConfirming(false);
    } else {
      // Era o último — re-busca a lista (fica vazia se tudo foi confirmado)
      await refetch();
      setConfirming(false);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        key="overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        className="fixed inset-0 z-[100] bg-background/85 backdrop-blur-sm flex items-center justify-center p-4"
      >
        <motion.div
          key={current.id}
          initial={{ opacity: 0, y: 20, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -10, scale: 0.96 }}
          transition={{ type: "spring", duration: 0.4 }}
          className={`w-full max-w-lg rounded-2xl border-2 ${config.borderColor} bg-card shadow-2xl overflow-hidden`}
        >
          {/* Header com badge + contador */}
          <div className="px-6 pt-5 pb-3 flex items-center justify-between">
            <span
              className={`inline-flex items-center gap-1.5 ${config.badgeBg} ${config.badgeText} text-xs font-semibold px-2.5 py-1 rounded-full`}
            >
              <span className={config.iconColor}>
                <Icon className="w-3.5 h-3.5" />
              </span>
              {config.badgeLabel}
            </span>
            {total > 1 && (
              <span className="text-xs text-muted-foreground font-medium">
                {currentIndex + 1} de {total}
              </span>
            )}
          </div>

          {/* Ícone grande */}
          <div className="px-6 pb-2 flex justify-center">
            <div
              className={`w-16 h-16 rounded-2xl ${config.iconBg} flex items-center justify-center`}
            >
              <Icon className={`w-8 h-8 ${config.iconColor}`} />
            </div>
          </div>

          {/* Título e mensagem */}
          <div className="px-6 pb-5 text-center">
            <h2 className="text-xl font-bold text-foreground mb-3">
              {current.title}
            </h2>
            <div className="text-sm text-muted-foreground leading-relaxed whitespace-pre-line">
              {current.message}
            </div>
          </div>

          {/* Divisor */}
          <div className="border-t border-border/50" />

          {/* Botão Entendi (sempre obrigatório) */}
          <div className="p-4">
            <button
              onClick={handleAcknowledge}
              disabled={confirming}
              className="w-full gradient-primary text-primary-foreground font-semibold py-3 rounded-lg hover:opacity-90 transition flex items-center justify-center gap-2 disabled:opacity-60"
            >
              {confirming ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Confirmando...
                </>
              ) : (
                <>
                  Entendi
                  {total > 1 && currentIndex < total - 1 && (
                    <span className="text-xs opacity-75">
                      ({currentIndex + 1}/{total})
                    </span>
                  )}
                </>
              )}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};

export default AnnouncementBlockingModal;
