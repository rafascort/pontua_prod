// frontend/src/components/ReferralCard.tsx
//
// Card PERMANENTE de indicação, sempre o primeiro no modal e na página /promocoes.
// v3: comunicação clara sobre cap mensal + projeção multi-meses
// v4: código de indicação destacado e copiável separado do link

import { useState } from "react";
import {
  Users, Copy, Check, Share2, MessageCircle, Loader2,
  ChevronDown, Calendar, Sparkles, Hash,
} from "lucide-react";
import { toast } from "sonner";
import { useReferralStats } from "@/hooks/useReferralStats";

interface Props {
  variant?: "modal" | "full";
}

const ReferralCard = ({ variant = "modal" }: Props) => {
  const { stats, isLoading } = useReferralStats();
  const [copiedCode, setCopiedCode] = useState(false);
  const [copiedLink, setCopiedLink] = useState(false);
  const [howItWorksOpen, setHowItWorksOpen] = useState(false);

  const handleCopyCode = async () => {
    if (!stats?.referral_code) return;
    try {
      await navigator.clipboard.writeText(stats.referral_code);
      setCopiedCode(true);
      toast.success("Código copiado!");
      setTimeout(() => setCopiedCode(false), 2500);
    } catch {
      toast.error("Não foi possível copiar. Copie manualmente.");
    }
  };

  const handleCopyLink = async () => {
    if (!stats?.referral_link) return;
    try {
      await navigator.clipboard.writeText(stats.referral_link);
      setCopiedLink(true);
      toast.success("Link copiado!");
      setTimeout(() => setCopiedLink(false), 2500);
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
      handleCopyLink();
    }
  };

  // ── Cálculos de projeção multi-meses ────────────────────────────
  const maxPctMonth = stats?.max_monthly_discount_pct ?? 40;
  const pctPerConv = stats?.pct_per_conversion ?? 10;
  const maxConvPerMonth = Math.floor(maxPctMonth / pctPerConv); // = 4
  const credits = stats?.discount_credits ?? 0;

  const buildProjection = (totalCredits: number): number[] => {
    const months: number[] = [];
    let remaining = totalCredits;
    while (remaining > 0) {
      const used = Math.min(remaining, maxConvPerMonth);
      months.push(used * pctPerConv);
      remaining -= used;
    }
    return months;
  };

  const projection = buildProjection(credits);
  const totalMonthsAhead = projection.length;
  const totalPctSum = projection.reduce((sum, p) => sum + p, 0);

  const remainingToMax = Math.max(0, maxConvPerMonth - (stats?.converted_count ?? 0));

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
          Até {maxPctMonth}% OFF/mês
        </span>
      </div>

      <h3 className={`${titleSize} font-semibold text-foreground mb-1`}>
        Indique amigos e ganhe 10% por assinatura
      </h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-2">
        Compartilhe seu link ou código. Para cada pessoa que assinar um plano pago,
        você ganha <strong className="text-foreground font-semibold">10% de desconto</strong> na
        sua mensalidade — acumulativo até <strong className="text-foreground font-semibold">40%/mês</strong>.
      </p>
      <p className="text-xs text-muted-foreground leading-relaxed mb-4">
        Indicou mais que 4 no mês? Tranquilo — o desconto extra é{" "}
        <strong className="text-foreground">guardado e aplicado nos meses seguintes</strong>,
        até zerar. Você nunca perde nada.
      </p>

      {/* Botão "Como funciona?" */}
      <button
        onClick={() => setHowItWorksOpen(!howItWorksOpen)}
        className="text-xs text-emerald-600 dark:text-emerald-400 hover:underline mb-3 flex items-center gap-1"
      >
        <ChevronDown
          className={`w-3.5 h-3.5 transition-transform ${howItWorksOpen ? "rotate-180" : ""}`}
        />
        {howItWorksOpen ? "Ocultar exemplos" : "Como funciona? Ver exemplos"}
      </button>

      {howItWorksOpen && (
        <div className="mb-4 p-3 rounded-lg bg-background/60 border border-border/40 space-y-3">
          <ExampleRow
            label="3 indicações no mês"
            months={[30]}
            note="3 × 10% = 30% de desconto, tudo no mês 1"
          />
          <ExampleRow
            label="7 indicações no mês"
            months={[40, 30]}
            note="40% no mês 1 (teto) + 30% no mês 2"
          />
          <ExampleRow
            label="12 indicações no mês"
            months={[40, 40, 40]}
            note="3 meses seguidos com desconto máximo"
          />
          <p className="text-[11px] text-muted-foreground pt-2 border-t border-border/40">
            <Sparkles className="w-3 h-3 inline mr-1 text-emerald-500" />
            Indicações que você fizer nos próximos meses se somam aos créditos
            que ainda estão guardados.
          </p>
        </div>
      )}

      {/* ── NOVO: Código de indicação destacado ───────────────────── */}
      <div className="mb-3">
        <div className="flex items-center gap-1.5 mb-1.5">
          <Hash className="w-3 h-3 text-muted-foreground" />
          <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
            Seu código
          </span>
        </div>
        <div className="bg-background/80 rounded-lg border border-emerald-500/30 flex items-center gap-2 p-2.5">
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground mx-auto" />
          ) : (
            <>
              <div className="flex-1 min-w-0 font-mono text-base font-bold text-foreground tracking-wider truncate">
                {stats?.referral_code ?? "—"}
              </div>
              <button
                onClick={handleCopyCode}
                disabled={!stats?.referral_code}
                className="text-xs font-medium px-3 py-1.5 rounded-md bg-emerald-500 text-white hover:bg-emerald-600 transition flex items-center gap-1.5 shrink-0 disabled:opacity-40"
              >
                {copiedCode ? (
                  <><Check className="w-3.5 h-3.5" /> Copiado</>
                ) : (
                  <><Copy className="w-3.5 h-3.5" /> Copiar código</>
                )}
              </button>
            </>
          )}
        </div>
        <p className="text-[11px] text-muted-foreground mt-1.5 px-1">
          Quem se cadastrar pode digitar este código manualmente em "Minhas Indicações" para vincular a indicação.
        </p>
      </div>

      {/* ── Link completo ─────────────────────────────────────────── */}
      <div className="mb-3">
        <div className="flex items-center gap-1.5 mb-1.5">
          <Share2 className="w-3 h-3 text-muted-foreground" />
          <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
            Ou compartilhe o link direto
          </span>
        </div>
        <div className="bg-background/80 rounded-lg border border-border/50 flex items-center gap-2 p-2.5">
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground mx-auto" />
          ) : (
            <>
              <div className="flex-1 min-w-0 text-xs font-mono text-muted-foreground truncate">
                {stats?.referral_link ?? "Carregando..."}
              </div>
              <button
                onClick={handleCopyLink}
                disabled={!stats?.referral_link}
                className="text-xs font-medium px-3 py-1.5 rounded-md bg-foreground text-background hover:opacity-90 transition flex items-center gap-1.5 shrink-0 disabled:opacity-40"
              >
                {copiedLink ? (
                  <><Check className="w-3.5 h-3.5" /> Copiado</>
                ) : (
                  <><Copy className="w-3.5 h-3.5" /> Copiar</>
                )}
              </button>
            </>
          )}
        </div>
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

      {/* Stats principais */}
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

      {/* Projeção multi-meses (só aparece se houver créditos) */}
      {credits > 0 && totalMonthsAhead > 0 && (
        <div className="mt-4 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30">
          <div className="flex items-center gap-1.5 mb-2.5">
            <Calendar className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
            <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">
              Próximas faturas com desconto
            </span>
          </div>

          <div className="flex gap-1.5 mb-2.5 overflow-x-auto pb-1">
            {projection.map((pct, idx) => (
              <div
                key={idx}
                className="flex-1 min-w-[60px] rounded-md bg-background/80 border border-emerald-500/20 px-2 py-1.5 text-center"
              >
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  {idx === 0 ? "este mês" : `mês ${idx + 1}`}
                </div>
                <div className="text-sm font-bold text-emerald-600 dark:text-emerald-400">
                  -{pct}%
                </div>
              </div>
            ))}
          </div>

          <div className="text-[11px] text-emerald-700 dark:text-emerald-300/90 leading-relaxed">
            Você tem{" "}
            <strong>
              {totalMonthsAhead} {totalMonthsAhead === 1 ? "mês" : "meses"} de
              desconto
            </strong>{" "}
            garantido(s) — total acumulado de{" "}
            <strong>{totalPctSum}% sobre a mensalidade</strong>.
          </div>
        </div>
      )}
    </div>
  );
};

const ExampleRow = ({
  label,
  months,
  note,
}: {
  label: string;
  months: number[];
  note: string;
}) => (
  <div>
    <div className="flex items-center justify-between mb-1.5">
      <span className="text-xs font-medium text-foreground">{label}</span>
      <div className="flex gap-1">
        {months.map((pct, i) => (
          <span
            key={i}
            className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
          >
            -{pct}%
          </span>
        ))}
      </div>
    </div>
    <div className="text-[11px] text-muted-foreground pl-1">{note}</div>
  </div>
);

export default ReferralCard;
