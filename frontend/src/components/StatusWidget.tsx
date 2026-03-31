// frontend/src/components/StatusWidget.tsx
//
// Formato de exibição:
//
//  ABAIXO DO LIMITE  →  "200 restantes"  barra colorida
//  EXATAMENTE NO LIMITE (paid)  →  "500 / 500  +0"  barra âmbar
//  ACIMA DO LIMITE (paid)  →  "500 / 500  +30"  barra âmbar + overflow
//  FREE ESGOTADO  →  "Esgotado"  barra vermelha  badge "Assinar"

interface StatusWidgetProps {
  planName:    string;
  pageBalance: number;   // páginas restantes dentro do plano
  pageLimit:   number;   // limite incluído
  extraPages:  number;   // páginas além do limite
  planStatus:  string;
  pageCount:   number;   // total de páginas usadas
  isLoading?:  boolean;
}

const ACTIVE_PLANS = ["basic", "standard", "premium"];

const StatusWidget = ({
  planName,
  pageBalance,
  pageLimit,
  extraPages,
  planStatus,
  pageCount,
  isLoading,
}: StatusWidgetProps) => {

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-secondary/60 border border-border/40 animate-pulse h-8 w-44" />
    );
  }

  const isFree      = planStatus === "free";
  const isPaid      = ACTIVE_PLANS.includes(planStatus);
  const isPastDue   = planStatus === "past_due";

  // Plano pago com todas as páginas incluídas usadas (pode ter ou não extras)
  const paidAtOrOverLimit = isPaid && pageBalance <= 0;
  const freeExhausted     = isFree && pageBalance <= 0;

  // Percentual da barra (só dentro do limite)
  const pagesUsedInPlan = Math.min(pageCount - extraPages, pageLimit);
  const fillPct = pageLimit > 0
    ? Math.min(100, Math.round((pagesUsedInPlan / pageLimit) * 100))
    : 0;

  // Cor da barra
  const barColor =
    freeExhausted        ? "bg-destructive/70"
    : paidAtOrOverLimit  ? "bg-amber-400/70"
    : fillPct >= 90      ? "bg-amber-500"
    :                      "bg-primary";

  // Chip do plano
  const chipClass =
    planStatus === "free"       ? "bg-primary/15 text-primary"
    : planStatus === "basic"    ? "bg-blue-500/15 text-blue-400"
    : planStatus === "standard" ? "bg-purple-500/15 text-purple-400"
    : planStatus === "premium"  ? "bg-amber-500/15 text-amber-400"
    : planStatus === "past_due" ? "bg-destructive/15 text-destructive"
    :                             "bg-secondary text-muted-foreground";

  // ── Layout condicional ────────────────────────────────────────────────
  //
  // Caso A: plano pago no limite ou com extras  →  "500 / 500  +0"
  // Caso B: free esgotado                       →  "Esgotado"
  // Caso C: normal                              →  "200 restantes  500 pág."

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-background/60 border border-border/40 backdrop-blur-sm">

      {/* Chip */}
      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap shrink-0 ${chipClass}`}>
        {planName}
      </span>

      <div className="w-px h-4 bg-border/50 shrink-0" />

      {/* ── CASO A: pago no limite / com extras ─────────────────────── */}
      {paidAtOrOverLimit ? (
        <div className="flex items-center gap-2">
          {/* Barra compacta */}
          <div className="relative h-[3px] rounded-full bg-border/40 overflow-visible" style={{ width: 48 }}>
            <div className={`absolute left-0 top-0 h-full rounded-full ${barColor}`} style={{ width: "100%" }} />
            {extraPages > 0 && (
              <div
                className="absolute top-0 h-full rounded-r-full bg-amber-400/50"
                style={{
                  left:  "100%",
                  width: Math.min(18, Math.max(4, Math.round((extraPages / pageLimit) * 60))) + "px",
                }}
              />
            )}
          </div>
          {/* Contador  "500 / 500  +0" */}
          <span className="text-[11px] font-semibold text-amber-400 whitespace-nowrap tabular-nums">
            {pageLimit.toLocaleString("pt-BR")}
            <span className="text-muted-foreground font-normal"> / {pageLimit.toLocaleString("pt-BR")}</span>
            {"  "}
            <span className={extraPages > 0 ? "text-amber-400" : "text-muted-foreground"}>
              +{extraPages.toLocaleString("pt-BR")}
            </span>
          </span>
        </div>
      ) : freeExhausted ? (
        /* ── CASO B: free esgotado ──────────────────────────────────── */
        <div className="flex flex-col gap-0.5" style={{ minWidth: 70 }}>
          <span className="text-[10px] font-medium text-destructive leading-none">Esgotado</span>
          <div className="h-[3px] rounded-full bg-destructive/70" />
        </div>
      ) : (
        /* ── CASO C: normal ─────────────────────────────────────────── */
        <div className="flex flex-col gap-0.5" style={{ minWidth: 90 }}>
          <div className="flex items-center justify-between gap-2">
            <span className={`text-[10px] leading-none font-medium whitespace-nowrap ${fillPct >= 90 ? "text-amber-500" : "text-foreground"}`}>
              {pageBalance.toLocaleString("pt-BR")} restantes
            </span>
            <span className="text-[10px] leading-none text-muted-foreground whitespace-nowrap">
              {pageLimit.toLocaleString("pt-BR")} pág.
            </span>
          </div>
          <div className="relative h-[3px] rounded-full bg-border/40">
            <div
              className={`absolute left-0 top-0 h-full rounded-full transition-all duration-500 ${barColor}`}
              style={{ width: `${fillPct}%` }}
            />
          </div>
        </div>
      )}

      {/* Badge "Assinar" — só free esgotado */}
      {freeExhausted && (
        <>
          <div className="w-px h-4 bg-border/50 shrink-0" />
          <a
            href="/#pricing"
            className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-primary/15 text-primary whitespace-nowrap shrink-0 hover:bg-primary/25 transition-colors"
          >
            Assinar
          </a>
        </>
      )}

      {/* Badge past_due */}
      {isPastDue && (
        <>
          <div className="w-px h-4 bg-border/50 shrink-0" />
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-destructive/15 text-destructive whitespace-nowrap shrink-0">
            Pgto. pendente
          </span>
        </>
      )}
    </div>
  );
};

export default StatusWidget;
