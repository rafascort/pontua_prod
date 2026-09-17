// frontend/src/novo/Pecas.tsx
//
// As pecas que as duas telas de extrator compartilham. Nada aqui fala com a
// API — sao so' forma. A logica continua dentro de cada tela, igual a' atual.

import { ReactNode, useRef, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CreditCard, FileText, Loader2, Upload, X } from "lucide-react";
import { toast } from "sonner";
import { useUserPlan } from "@/hooks/useUserPlan";

/* ------------------------------------------------------------------ cartao */

export function CartaoPlano({ vaiConsumir }: { vaiConsumir: number }) {
  const { plan, canUseExtras } = useUserPlan();

  const usadas = plan.pageCount;
  const limite = plan.pageLimit || 1;
  const pct = Math.min(100, Math.round((usadas / limite) * 100));
  const estouro = Math.max(0, usadas - limite);

  return (
    <div className="glass-card p-[22px]">
      <div className="font-semibold text-foreground">Seu plano</div>
      <p className="mb-4 mt-0.5 text-[12.5px] text-muted-foreground">
        {plan.planName} · {limite} páginas por mês
      </p>

      <div className="h-[9px] overflow-hidden rounded-[5px] bg-muted-foreground/15">
        <div
          className="h-full rounded-[5px] gradient-primary transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-[7px] flex justify-between text-xs text-muted-foreground">
        <span>{usadas} usadas</span>
        <span>
          {plan.pageBalance > 0
            ? `${plan.pageBalance} restantes`
            : canUseExtras
              ? `${estouro} extras neste ciclo`
              : "saldo esgotado"}
        </span>
      </div>

      {vaiConsumir > 0 && (
        <div className="mt-4 rounded-lg border border-border/60 bg-secondary/25 px-3.5 py-2.5 text-[12.5px]">
          {canUseExtras ? (
            plan.pageBalance >= vaiConsumir ? (
              <span className="text-muted-foreground">
                <b className="text-foreground">{vaiConsumir} páginas</b> nesta extração ·
                restam {plan.pageBalance - vaiConsumir} depois
              </span>
            ) : (
              <span className="text-warning">
                {plan.pageBalance > 0
                  ? `${plan.pageBalance} incluídas + ${vaiConsumir - plan.pageBalance} extras`
                  : `${vaiConsumir} páginas serão cobradas como extras`}
              </span>
            )
          ) : plan.pageBalance >= vaiConsumir ? (
            <span className="text-muted-foreground">
              <b className="text-foreground">{vaiConsumir} páginas</b> nesta extração ·
              restam {plan.pageBalance - vaiConsumir} depois
            </span>
          ) : (
            <span className="text-destructive">
              Saldo insuficiente: precisa de {vaiConsumir}, tem {plan.pageBalance}
            </span>
          )}
        </div>
      )}

      {!canUseExtras && plan.pageBalance <= 5 && plan.pageBalance > 0 && (
        <p className="mt-3 text-xs font-medium text-warning">
          ⚠ Saldo baixo — {plan.pageBalance} página(s) restante(s)
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ etapas */

export function ComoFunciona({
  um,
  dois,
  saida,
}: {
  um: string;
  dois: string;
  saida: string;
}) {
  const passo = (n: number, texto: string) => (
    <li className="flex gap-3">
      <span className="mt-[1px] flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full border border-primary/40 bg-primary/[0.12] text-[11.5px] font-bold text-primary">
        {n}
      </span>
      <span className="text-[13px] leading-snug text-foreground">{texto}</span>
    </li>
  );

  return (
    <div className="glass-card p-[22px]">
      <div className="mb-3.5 font-semibold text-foreground">Como funciona</div>
      <ol className="space-y-3">
        {passo(1, um)}
        {passo(2, dois)}
      </ol>
      <div className="mt-4 border-t border-border/60 pt-3.5 text-[12.5px] text-muted-foreground">
        {saida}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ upload */

export function AreaUpload({
  arquivo,
  aoEscolher,
  desabilitado,
  icone,
}: {
  arquivo: File | null;
  aoEscolher: (f: File) => void;
  desabilitado: boolean;
  icone: ReactNode;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [arrastando, setArrastando] = useState(false);

  const aceitar = (f?: File | null) => {
    if (!f) return;
    if (f.type !== "application/pdf") {
      toast.error("Selecione um arquivo PDF válido.");
      return;
    }
    aoEscolher(f);
    toast.success(`PDF "${f.name}" importado.`);
  };

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); if (!desabilitado) setArrastando(true); }}
      onDragLeave={() => setArrastando(false)}
      onDrop={(e) => {
        e.preventDefault();
        setArrastando(false);
        if (!desabilitado) aceitar(e.dataTransfer.files?.[0]);
      }}
    >
      <input
        ref={input}
        type="file"
        accept=".pdf"
        className="hidden"
        onChange={(e) => { aceitar(e.target.files?.[0]); e.target.value = ""; }}
      />
      <button
        type="button"
        onClick={() => input.current?.click()}
        disabled={desabilitado}
        className={`w-full rounded-xl border border-dashed px-[22px] py-[26px] text-center transition-all disabled:cursor-not-allowed disabled:opacity-50 ${
          arrastando
            ? "border-primary bg-primary/10"
            : "border-border/90 hover:border-primary/50 hover:bg-primary/5"
        }`}
      >
        {arquivo ? (
          <>
            <FileText className="mx-auto h-9 w-9 text-primary" />
            <div className="mt-2.5 font-semibold text-foreground">{arquivo.name}</div>
            <p className="mt-1.5 text-[12.5px] text-muted-foreground">
              {(arquivo.size / 1024 / 1024).toFixed(1)} MB — clique ou arraste outro para trocar
            </p>
          </>
        ) : (
          <>
            <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl border border-primary/25 bg-primary/[0.1] text-primary">{icone}</div>
            <div className="mt-2 font-semibold text-foreground">Arraste o PDF aqui</div>
            <p className="mb-3.5 mt-1 text-[12.5px] text-muted-foreground">
              ou clique para escolher
            </p>
            <span className="inline-flex items-center gap-2 rounded-lg border border-transparent gradient-primary px-4 py-2 text-[13px] font-semibold text-primary-foreground">
              <Upload className="h-4 w-4" /> Escolher arquivo
            </span>
          </>
        )}
      </button>
    </div>
  );
}

/* --------------------------------------------------------------- progresso */

export function Progresso({
  titulo,
  mensagem,
  atual,
  total,
}: {
  titulo: string;
  mensagem: string;
  atual: number;
  total: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 p-4 backdrop-blur-sm"
    >
      <motion.div
        initial={{ scale: 0.95, y: 10 }}
        animate={{ scale: 1, y: 0 }}
        className="glass-card w-full max-w-sm p-8 text-center"
      >
        <Loader2 className="mx-auto mb-4 h-12 w-12 animate-spin text-primary" />
        <h3 className="mb-2 text-lg font-bold text-foreground">{titulo}</h3>
        <p className="mb-4 text-sm text-muted-foreground">{mensagem}</p>
        {total > 0 && (
          <>
            <div className="mb-2 h-2 w-full rounded-full bg-secondary/60">
              <div
                className="h-2 rounded-full gradient-primary transition-all duration-500"
                style={{ width: `${Math.round((atual / total) * 100)}%` }}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              Página {atual} de {total}
            </p>
          </>
        )}
      </motion.div>
    </motion.div>
  );
}

/* ------------------------------------------------------------- saldo curto */

export function ModalSaldo({
  pedidas,
  disponiveis,
  aoFechar,
}: {
  pedidas: number;
  disponiveis: number;
  aoFechar: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 p-4 backdrop-blur-sm"
    >
      <motion.div
        initial={{ scale: 0.95, y: 10 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.95, y: 10 }}
        className="glass-card relative w-full max-w-md p-8"
      >
        <button
          onClick={aoFechar}
          className="absolute right-4 top-4 text-muted-foreground hover:text-foreground"
        >
          <X className="h-5 w-5" />
        </button>
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-warning/15">
            <AlertTriangle className="h-8 w-8 text-warning" />
          </div>
          <h3 className="mb-2 text-xl font-bold text-foreground">Saldo insuficiente</h3>
          <p className="mb-2 text-sm text-muted-foreground">
            {disponiveis === 0
              ? "Suas páginas grátis foram totalmente utilizadas."
              : `Você precisa de ${pedidas} página(s), mas tem apenas ${disponiveis} disponível(is).`}
          </p>
          <p className="mb-6 text-xs text-muted-foreground">
            Assine um plano para continuar processando.
          </p>
          <div className="flex gap-3">
            <button
              onClick={aoFechar}
              className="flex-1 rounded-lg border border-border py-3 text-sm font-medium text-foreground transition-all hover:bg-surface-hover"
            >
              Fechar
            </button>
            <a href="/#pricing" className="flex-1">
              <button className="flex w-full items-center justify-center gap-2 rounded-lg gradient-primary py-3 text-sm font-bold text-primary-foreground transition-all hover:shadow-lg hover:shadow-primary/25">
                <CreditCard className="h-4 w-4" /> Ver planos
              </button>
            </a>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
