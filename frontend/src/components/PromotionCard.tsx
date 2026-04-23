// frontend/src/components/PromotionCard.tsx
//
// Componente reutilizável de card de promoção.
// Usado no modal semanal, na página /promocoes e no preview do admin.

import { useState } from "react";
import {
  Copy, Check, ExternalLink, MessageCircle, Mail,
  Sparkles, Gift, Zap, Star, Trophy, Tag, Percent,
  Rocket, Flame, Heart, Crown, PartyPopper, Megaphone,
  Calendar, TrendingUp, Award, ShieldCheck,
  LucideIcon,
} from "lucide-react";
import { toast } from "sonner";
import type { Promotion } from "@/hooks/usePromotions";
import { trackPromotionEvent } from "@/hooks/usePromotions";

const ICON_MAP: Record<string, LucideIcon> = {
  Sparkles, Gift, Zap, Star, Trophy, Tag, Percent,
  Rocket, Flame, Heart, Crown, PartyPopper, Megaphone,
  Calendar, TrendingUp, Award, ShieldCheck,
};

const COLOR_MAP: Record<string, { border: string; bg: string; badge: string; text: string }> = {
  emerald: {
    border: "border-l-emerald-500/80",
    bg: "bg-emerald-500/5",
    badge: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
    text: "text-emerald-600 dark:text-emerald-400",
  },
  indigo: {
    border: "border-l-indigo-500/80",
    bg: "bg-indigo-500/5",
    badge: "bg-indigo-500/15 text-indigo-600 dark:text-indigo-400",
    text: "text-indigo-600 dark:text-indigo-400",
  },
  amber: {
    border: "border-l-amber-500/80",
    bg: "bg-amber-500/5",
    badge: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
    text: "text-amber-600 dark:text-amber-400",
  },
  rose: {
    border: "border-l-rose-500/80",
    bg: "bg-rose-500/5",
    badge: "bg-rose-500/15 text-rose-600 dark:text-rose-400",
    text: "text-rose-600 dark:text-rose-400",
  },
  blue: {
    border: "border-l-blue-500/80",
    bg: "bg-blue-500/5",
    badge: "bg-blue-500/15 text-blue-600 dark:text-blue-400",
    text: "text-blue-600 dark:text-blue-400",
  },
  violet: {
    border: "border-l-violet-500/80",
    bg: "bg-violet-500/5",
    badge: "bg-violet-500/15 text-violet-600 dark:text-violet-400",
    text: "text-violet-600 dark:text-violet-400",
  },
  teal: {
    border: "border-l-teal-500/80",
    bg: "bg-teal-500/5",
    badge: "bg-teal-500/15 text-teal-600 dark:text-teal-400",
    text: "text-teal-600 dark:text-teal-400",
  },
  slate: {
    border: "border-l-slate-500/80",
    bg: "bg-slate-500/5",
    badge: "bg-slate-500/15 text-slate-600 dark:text-slate-400",
    text: "text-slate-600 dark:text-slate-400",
  },
};

const WHATSAPP_SUPORTE = "https://wa.me/5554999427282";
const EMAIL_SUPORTE = "suporte@sistemaponto.com";

interface Props {
  promotion: Promotion;
  variant?: "modal" | "full" | "preview";
  disableTracking?: boolean;
}

const PromotionCard = ({ promotion: p, variant = "modal", disableTracking = false }: Props) => {
  const [codeCopied, setCodeCopied] = useState(false);

  const Icon = ICON_MAP[p.icon] ?? Sparkles;
  const colors = COLOR_MAP[p.badge_color] ?? COLOR_MAP.emerald;

  const handleCtaClick = () => {
    if (!disableTracking) {
      trackPromotionEvent(p.id, "cta_click");
    }
  };

  const handleCopyCode = async () => {
    if (!p.cta_value) return;
    try {
      await navigator.clipboard.writeText(p.cta_value);
      setCodeCopied(true);
      toast.success(`Código ${p.cta_value} copiado!`);
      handleCtaClick();
      setTimeout(() => setCodeCopied(false), 2500);
    } catch {
      toast.error("Não foi possível copiar.");
    }
  };

  const isFullVariant = variant === "full";
  const padding = isFullVariant ? "p-6" : "p-5";
  const titleSize = isFullVariant ? "text-lg" : "text-base";

  return (
    <div
      className={`rounded-xl border border-border/50 border-l-[3px] ${colors.border} ${colors.bg} ${padding}`}
    >
      {/* Badge + hint */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <span
          className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded ${colors.badge}`}
        >
          <Icon className="w-3 h-3" />
          {p.badge_label}
        </span>
        {p.discount_hint && (
          <span className="text-xs text-muted-foreground">{p.discount_hint}</span>
        )}
      </div>

      {/* Título */}
      <h3 className={`${titleSize} font-semibold text-foreground mb-1`}>
        {p.title}
      </h3>

      {/* Descrição */}
      <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap mb-4">
        {p.description}
      </p>

      {/* CTA */}
      {p.cta_type === "contact" && (
        <div className="bg-background/80 rounded-lg border border-border/50 p-3 flex items-stretch gap-3">
          <a
            href={WHATSAPP_SUPORTE}
            target="_blank"
            rel="noopener noreferrer"
            onClick={handleCtaClick}
            className="flex-1 flex flex-col gap-0.5 hover:bg-muted/30 transition rounded p-1.5 -m-1.5"
          >
            <span className="text-[11px] text-muted-foreground flex items-center gap-1">
              <MessageCircle className="w-3 h-3" />
              WhatsApp
            </span>
            <span className="text-xs font-medium text-foreground">
              (54) 99942-7282
            </span>
          </a>
          <div className="w-px bg-border/50" />
          <a
            href={`mailto:${EMAIL_SUPORTE}?subject=${encodeURIComponent(p.title)}`}
            onClick={handleCtaClick}
            className="flex-1 flex flex-col gap-0.5 hover:bg-muted/30 transition rounded p-1.5 -m-1.5"
          >
            <span className="text-[11px] text-muted-foreground flex items-center gap-1">
              <Mail className="w-3 h-3" />
              E-mail
            </span>
            <span className="text-xs font-medium text-foreground truncate">
              {EMAIL_SUPORTE}
            </span>
          </a>
        </div>
      )}

      {p.cta_type === "link" && p.cta_value && (
        <a
          href={p.cta_value}
          target={p.cta_value.startsWith("http") ? "_blank" : undefined}
          rel={p.cta_value.startsWith("http") ? "noopener noreferrer" : undefined}
          onClick={handleCtaClick}
          className={`inline-flex items-center gap-1.5 text-sm font-medium px-4 py-2 rounded-md ${colors.badge} hover:opacity-80 transition`}
        >
          {p.cta_label ?? "Saber mais"}
          <ExternalLink className="w-3.5 h-3.5" />
        </a>
      )}

      {p.cta_type === "code" && p.cta_value && (
        <div>
          <p className="text-xs text-muted-foreground mb-1.5">
            {p.cta_label ?? "Use o código:"}
          </p>
          <button
            onClick={handleCopyCode}
            className="bg-background/80 rounded-lg border border-dashed border-border hover:border-foreground/30 flex items-center gap-3 p-3 w-full transition group"
          >
            <span className="font-mono text-base font-semibold text-foreground flex-1 text-left tracking-wider">
              {p.cta_value}
            </span>
            <span className="text-xs font-medium text-muted-foreground group-hover:text-foreground transition flex items-center gap-1">
              {codeCopied ? (
                <><Check className="w-3.5 h-3.5" /> Copiado</>
              ) : (
                <><Copy className="w-3.5 h-3.5" /> Copiar</>
              )}
            </span>
          </button>
        </div>
      )}

      {/* Data de expiração (variant full) */}
      {isFullVariant && p.ends_at && (
        <p className="text-xs text-muted-foreground mt-3 flex items-center gap-1">
          <Calendar className="w-3 h-3" />
          Válido até {formatEndDate(p.ends_at)}
        </p>
      )}
    </div>
  );
};

function formatEndDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "long",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

export default PromotionCard;
