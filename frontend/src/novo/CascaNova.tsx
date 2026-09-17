// frontend/src/novo/CascaNova.tsx
//
// A casca do layout novo: fundo com brilho, o AppHeader que ja' existe, a
// barra de modulos e, quando o modulo tem mais de uma tela, a barra de abas.
//
// O AppHeader e' reaproveitado de proposito. Ele carrega o menu de conta, os
// links de empresa, indicacoes, assinatura e o logout — 293 linhas que ja'
// funcionam. Refazer aquilo so' para mudar o visual seria arriscar quebrar
// coisa que nao tem nada a ver com o extrator.

import { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import AppHeader from "@/components/AppHeader";
import { useAuth } from "@/contexts/AuthContext";

const MODULOS = [
  { rotulo: "Extrator de Ponto", para: "/app/ponto" },
  { rotulo: "Extrator de Holerite", para: "/app/holerite" },
  { rotulo: "Perícias", para: "/pericias" },
];

export interface Aba {
  rotulo: string;
  para?: string;      // sem `para` = ainda nao existe, aparece apagada
  n?: number;         // contador ao lado do rotulo
}

const ITEM =
  "shrink-0 rounded-lg px-3 py-1.5 text-[13.5px] font-medium transition-colors";
const ITEM_ATIVO =
  "bg-primary/[0.13] text-foreground shadow-[inset_0_0_0_1px_hsl(var(--primary)/0.28)]";
const ITEM_INATIVO =
  "text-muted-foreground hover:bg-secondary/60 hover:text-foreground";

// Rola na horizontal em vez de empilhar: empilhado, a barra crescia e passava
// por cima do titulo da pagina no celular.
const BARRA =
  "mx-auto flex min-h-[46px] max-w-[1220px] items-center gap-1 overflow-x-auto " +
  "whitespace-nowrap px-5 [-ms-overflow-style:none] [scrollbar-width:none] " +
  "[&::-webkit-scrollbar]:hidden";

function BarraModulos({ aoVoltarAntigo }: { aoVoltarAntigo?: () => void }) {
  const { pathname } = useLocation();
  const { user } = useAuth();

  return (
    <div className="border-b border-border/60 bg-background/40 backdrop-blur-sm">
      <div className={BARRA}>
        {MODULOS.map((m) => (
          <Link
            key={m.para}
            to={m.para}
            className={`${ITEM} ${pathname.startsWith(m.para) ? ITEM_ATIVO : ITEM_INATIVO}`}
          >
            {m.rotulo}
          </Link>
        ))}

        <span className="min-w-4 flex-1" />

        {/* O AppHeader nao tem link para o painel administrativo. Como o admin
            agora cai na Pericias ao entrar, sem isto o /admin ficaria so' por
            URL digitada. */}
        {user?.role === "admin" && (
          <Link
            to="/admin"
            className="mr-2 shrink-0 rounded-lg px-2.5 py-1 text-[11.5px] text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground"
          >
            Admin
          </Link>
        )}

        <span className="shrink-0 rounded-full border border-warning/35 bg-warning/[0.12] px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide text-warning">
          <span className="hidden sm:inline">layout novo · </span>só admin
        </span>
        {aoVoltarAntigo && (
          <button
            onClick={aoVoltarAntigo}
            className="ml-2 shrink-0 rounded-lg border border-border px-2.5 py-1 text-[11.5px] text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
          >
            ver o antigo
          </button>
        )}
      </div>
    </div>
  );
}

function BarraAbas({ abas, rodape }: { abas: Aba[]; rodape?: ReactNode }) {
  const { pathname } = useLocation();

  return (
    <div className="border-b border-border/50 bg-background/25">
      <div className={BARRA}>
        {abas.map((a) =>
          a.para ? (
            <Link
              key={a.rotulo}
              to={a.para}
              className={`${ITEM} ${pathname === a.para ? ITEM_ATIVO : ITEM_INATIVO}`}
            >
              {a.rotulo}
              {a.n !== undefined && <span className="ml-1.5 text-[11.5px] opacity-70">{a.n}</span>}
            </Link>
          ) : (
            <span
              key={a.rotulo}
              className={`${ITEM} cursor-default text-muted-foreground/45`}
              title="Ainda não construída"
            >
              {a.rotulo}
              <span className="ml-1.5 text-[10.5px] opacity-70">em breve</span>
            </span>
          )
        )}
        {rodape && (
          <>
            <span className="min-w-4 flex-1" />
            <span className="shrink-0 text-xs text-muted-foreground">{rodape}</span>
          </>
        )}
      </div>
    </div>
  );
}

export default function CascaNova({
  titulo,
  descricao,
  children,
  abas,
  rodapeAbas,
  aoVoltarAntigo,
}: {
  titulo: string;
  descricao: string;
  children: ReactNode;
  abas?: Aba[];
  rodapeAbas?: ReactNode;
  aoVoltarAntigo?: () => void;
}) {
  return (
    <div
      className="flex min-h-screen flex-col bg-background"
      style={{
        backgroundImage:
          "radial-gradient(1100px 520px at 12% -8%, hsl(213 100% 65% / .16), transparent 60%)," +
          "radial-gradient(900px 480px at 92% 4%, hsl(250 89% 68% / .13), transparent 62%)",
        backgroundAttachment: "fixed",
      }}
    >
      <AppHeader />
      <BarraModulos aoVoltarAntigo={aoVoltarAntigo} />
      {abas && <BarraAbas abas={abas} rodape={rodapeAbas} />}

      <main className="mx-auto w-full max-w-[1220px] flex-1 px-5 pb-24 pt-7">
        <h1 className="text-[23px] font-bold tracking-[-0.02em] text-foreground">{titulo}</h1>
        <p className="mb-5 max-w-[80ch] text-[12.8px] text-muted-foreground">{descricao}</p>
        {children}
      </main>
    </div>
  );
}
