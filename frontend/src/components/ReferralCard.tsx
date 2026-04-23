// frontend/src/components/ReferralCard.tsx
//
// Card PERMANENTE de indicação, sempre o primeiro no modal e na página /promocoes.
// Diferente dos cards dinâmicos, este tem estatísticas ao vivo e botões de ação.

import { useState } from "react";
import {
  Users, Copy, Check, Share2, TrendingUp, MessageCircle, Loader2,
} from "lucide-react";
import { toast } from "sonner";
import { useReferralStats } from "@/hooks/useReferralStats";

interface Props {
  variant?: "modal" | "full";
}

const ReferralCard = ({ variant = "modal" }: Props) => {
  const { stats, isLoading } = useReferralStats();
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!stats?.referral_link) return;
    try {
      await navigator.clipboard.writeText(stats.referral_link);
      setCopied(true);
      toast.success("Link copiado!");
      setTimeout(() => setCopied(false), 2500);
    } catch {
      toast.error("Não foi possível copiar. Copie manualmente.");
    }
  };

  const handleShareWhatsApp = () => {
    if (!stats?.referral_link) return;
    const msg = encodeURIComponent(
      `Estou usando o Sistema Ponto para extrair dados de cartões de ponto e ` +
      `holerites automaticamente com IA. Ganha 50 páginas grátis ao se cadastrar pelo meu link: ${stats.referral_link}`,
    );
    window.open(`https://wa.me/?text=${msg}`, "_blank");
  };

  const handleNativeShare = async () => {
    if (!stats?.referral_link) return;
    if (navigator.share) {
      try {
        await navigator.share({
          title: "Sistema Ponto",
          text: "Extração automática de cartões de ponto e holerites com IA",
          url: stats.referral_link,
        });
      } catch {
        // cancelado
      }
    } else {
      handleCopy();
    }
  };

  const maxConversions = stats
    ? Math.floor(stats.max_monthly_discount_pct / stats.pct_per_conversion)
    : 4;
  const remainingToMax = stats
    ? Math.max(0, maxConversions - stats.converted_count)
    : 4;

  const isFullVariant = variant === "full";
  const padding = isFullVariant ? "p-6" : "p-5";
  const titleSize = isFullVariant ? "text-lg" : "text-base";

  return (
    <div
      className={`rounded-xl border border-border/50 border-l-[3px] border-l-emerald-500/80 bg-emerald-500/5 ${padding}`}
    >
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <span className="inline-flex items-center gap-1 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 text-[11px] font-semibold px-2 py-1 rounded">
          <Users className="w-3 h-3" />
          Indicação
        </span>
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded">
          Permanente
        </span>
        <span className="text-xs text-muted-foreground ml-auto">
          Até {stats?.max_monthly_discount_pct ?? 40}% OFF
        </span>
      </div>

      <h3 className={`${titleSize} font-semibold text-foreground mb-1`}>
        Indique amigos e ganhe 10% por assinatura
      </h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        Compartilhe seu link. Para cada pessoa que assinar um plano pago através
        dele, você recebe <strong className="text-foreground font-semibold">10% de desconto</strong> na
        mensalidade — acumulativo até 40%. Acima disso, aplica no mês seguinte.
      </p>

      {/* Link */}
      <div className="bg-background/80 rounded-lg border border-border/50 flex items-center gap-2 p-2.5 mb-3">
        {isLoading ? (
          <Loader2 className="w-4 h-4 animate-spin text-muted-foreground mx-auto" />
        ) : (
          <>
            <div className="flex-1 min-w-0 text-xs font-mono text-muted-foreground truncate">
              {stats?.referral_link ?? "Carregando..."}
            </div>
            <button
              onClick={handleCopy}
              disabled={!stats?.referral_link}
              className="text-xs font-medium px-3 py-1.5 rounded-md bg-foreground text-background hover:opacity-90 transition flex items-center gap-1.5 shrink-0 disabled:opacity-40"
            >
              {copied ? (
                <><Check className="w-3.5 h-3.5" /> Copiado</>
              ) : (
                <><Copy className="w-3.5 h-3.5" /> Copiar</>
              )}
            </button>
          </>
        )}
      </div>

      {/* Compartilhar */}
      <div className="flex gap-2 mb-4">
        <button
          onClick={handleShareWhatsApp}
          disabled={!stats?.referral_link}
          className="flex-1 flex items-center justify-center gap-1.5 text-xs font-medium py-2 rounded-md bg-[#25D366]/10 text-[#1e9e4e] hover:bg-[#25D366]/20 transition disabled:opacity-40"
        >
          <MessageCircle className="w-3.5 h-3.5" />
          WhatsApp
        </button>
        <button
          onClick={handleNativeShare}
          disabled={!stats?.referral_link}
          className="flex-1 flex items-center justify-center gap-1.5 text-xs font-medium py-2 rounded-md border border-border/50 hover:bg-muted/50 transition disabled:opacity-40"
        >
          <Share2 className="w-3.5 h-3.5" />
          Compartilhar
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3 pt-3 border-t border-border/50">
        <div>
          <div className="text-xl font-bold text-foreground">
            {stats?.converted_count ?? "—"}
          </div>
          <div className="text-[11px] text-muted-foreground">convertidos</div>
        </div>
        <div>
          <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400">
            {stats?.active_discount_pct ?? 0}%
          </div>
          <div className="text-[11px] text-muted-foreground">desconto ativo</div>
        </div>
        <div>
          <div className="text-xl font-bold text-foreground">
            {remainingToMax > 0 ? `+${remainingToMax}` : "✓"}
          </div>
          <div className="text-[11px] text-muted-foreground">
            {remainingToMax > 0 ? "p/ máximo" : "máximo atingido"}
          </div>
        </div>
      </div>

      {stats && stats.next_month_discount_pct > 0 && (
        <div className="mt-3 text-xs text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5">
          <TrendingUp className="w-3.5 h-3.5" />
          +{stats.next_month_discount_pct}% extra aplicado no mês que vem
        </div>
      )}
    </div>
  );
};

export default ReferralCard;
