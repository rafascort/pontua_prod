// frontend/src/novo/PericiasPainel.tsx
//
// Painel de Pericias.
//
// O PJe e' a fonte da verdade e o sistema NAO opina. A tela mostra o que o
// tribunal declara — situacao, tarefa, prazo de entrega — e nada mais. Nao ha'
// selo de "confira", nao ha' juizo sobre de quem e' a bola: as versoes que
// tentaram isso erraram no acervo real, porque `tarefa` e' a esteira interna do
// cartorio ("Elaborar despacho" e' do servidor, nao do perito) e `prazoEntrega`
// e' fixado no aceite e nunca mais se mexe.
//
// O que separa o prazo de 2025 do prazo de sexta e' o HORIZONTE: por padrao,
// vencidos dos ultimos 60 dias e o que vence nos proximos 15. O resto fica a um
// clique. Foi o recorte do painel que o perito ja' usava.
//
// Juizo de valor so' vem dele, digitado: baixa e observacao.

import { ReactNode, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle, ArrowRight, CalendarClock, Check, Clock, HelpCircle, Loader2,
  Mail, Pencil, RefreshCw, Undo2,
} from "lucide-react";
import { toast } from "sonner";
import CascaNova, { Aba } from "./CascaNova";
import { buscar } from "./api";

export const ABAS_PERICIAS: Aba[] = [
  { rotulo: "Painel", para: "/pericias" },
  { rotulo: "Ligar o PJe", para: "/pericias/pje" },
  { rotulo: "Entrada por e-mail", para: "/pericias/entrada" },
  { rotulo: "Honorários" },
  { rotulo: "Acervo" },
];

interface Perito {
  configurado: boolean;
  nome_tribunal?: string;
  especialidade?: string;
  tribunais?: string[];
}

interface Item {
  id_pericia: number;
  processo: string;
  situacao_texto: string | null;
  tarefa: string | null;
  classe: string | null;
  orgao: string | null;
  partes: string | null;
  fase: string | null;
  prazo_entrega: string | null;
  data_aceite: string | null;
  expediente_aberto: boolean;
  ciencia_pendente: boolean;
  laudo_juntado: boolean;
  pode_esclarecimentos: boolean;
  baixa: string | null;
  observacao: string | null;
  dias: number | null;
}

interface Painel {
  tem_dados: boolean;
  horizonte: { atras: number; frente: number };
  ultimo_envio: { tribunal: string; perito_pje: string; recebido_em: string | null } | null;
  kpi: Record<string, number>;
  vencido: Item[]; correndo: Item[]; sem_prazo: Item[];
  esclarecimentos: Item[]; envelope: Item[]; ciencia: Item[]; fora: Item[];
}

const ESP: Record<string, string> = {
  contabil: "Contábil", medica: "Médica", engenharia: "Engenharia", outra: "Outra",
};

const BAIXAS: [string, string][] = [
  ["fiz", "Já fiz"],
  ["nao_meu", "Não é meu"],
  ["mandaram_nao_fazer", "Mandaram não fazer"],
  ["encerrado", "Processo encerrado"],
];

const HORIZONTES: [number, number, string][] = [
  [60, 15, "15 dias"],
  [60, 30, "30 dias"],
  [180, 90, "3 meses"],
  [3650, 3650, "tudo"],
];

function br(iso: string | null) {
  if (!iso) return "—";
  const [a, m, d] = iso.split("-");
  return `${d}/${m}/${a}`;
}

/* ------------------------------------------------------------------ passos */

function Passo({ n, feito, titulo, texto }: { n: number; feito: boolean; titulo: string; texto: string }) {
  return (
    <div className="flex gap-3">
      <span className={`mt-[1px] flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[12px] font-bold ${
        feito ? "border-success/50 bg-success/[0.14] text-success" : "border-primary/40 bg-primary/[0.12] text-primary"}`}>
        {n}
      </span>
      <div>
        <div className="text-sm font-semibold text-foreground">{titulo}</div>
        <div className="text-[12.5px] leading-snug text-muted-foreground">{texto}</div>
      </div>
    </div>
  );
}

function Configurar({ p, temRetrato }: { p: Perito; temRetrato: boolean }) {
  return (
    <div className="glass-card flex flex-col gap-9 p-8 lg:flex-row">
      <div className="flex-[1.2]">
        <div className="text-[18px] font-semibold tracking-[-0.01em] text-foreground">
          Vamos configurar o seu módulo
        </div>
        <p className="mb-7 mt-2 max-w-[56ch] text-[13px] text-muted-foreground">
          São dois passos. O primeiro leva dois minutos; o segundo é o que traz
          os prazos.
        </p>
        <div className="flex flex-col gap-5">
          <Passo n={1} feito={p.configurado} titulo="Quem é você no tribunal"
                 texto="Nome como o tribunal escreve, especialidade e onde você atua." />
          <Passo n={2} feito={temRetrato} titulo="Ligar o PJe"
                 texto="Um favorito no navegador lê a sua lista de perícias e manda para cá." />
        </div>
        <Link
          to={p.configurado ? "/pericias/pje" : "/pericias/cadastro"}
          className="mt-8 inline-flex items-center gap-2 rounded-xl gradient-primary px-6 py-3 text-sm font-bold text-primary-foreground transition-all hover:shadow-lg hover:shadow-primary/25"
        >
          {p.configurado ? "Ligar o PJe" : "Começar"} <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
      <div className="flex-1 border-border/60 lg:border-l lg:pl-9">
        <div className="mb-3.5 text-sm font-semibold text-foreground">O que aparece aqui</div>
        <div className="flex flex-col gap-3.5 text-[12.8px] text-muted-foreground">
          <div>Só o que o PJe declara: situação da perícia, tarefa do processo e a data de entrega que o próprio tribunal fixou.</div>
          <div>Nada é deduzido. Se o PJe não diz, o painel não inventa.</div>
          <div>Você marca baixa e escreve observação em cada linha — isso é seu, e sobrevive a toda atualização.</div>
        </div>
        <p className="mt-5 border-t border-border/60 pt-4 text-[12.5px] leading-relaxed text-muted-foreground">
          Não pedimos senha nem certificado. O favorito usa a sessão do PJe que
          você já abre no navegador, e só lê.
        </p>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- elementos */

function Kpi({ n, rotulo, sub, cor, icone, alvo }: {
  n: number | null; rotulo: string; sub: string; cor: string; icone: ReactNode; alvo: string;
}) {
  return (
    <a href={alvo} className="glass-card relative overflow-hidden p-[18px] transition-colors hover:border-primary/40">
      <span className="absolute inset-x-0 top-0 h-[2px] gradient-primary opacity-65" />
      <div className="flex items-start justify-between">
        <div className={`text-[30px] font-bold leading-[1.1] tracking-[-0.03em] ${n === null ? "text-muted-foreground" : cor}`}>
          {n === null ? "—" : n}
        </div>
        <span className={n === null ? "text-muted-foreground" : cor}>{icone}</span>
      </div>
      <div className="mt-1 font-medium text-foreground">{rotulo}</div>
      <div className="text-xs text-muted-foreground">{sub}</div>
    </a>
  );
}

function Tarja({ dias, fixa }: { dias: number | null; fixa?: string }) {
  let txt: string, cor: string;
  if (fixa) {
    txt = fixa; cor = "border-primary/40 bg-primary/[0.10] text-primary";
  } else if (dias === null) {
    txt = "sem data"; cor = "border-border bg-secondary/40 text-muted-foreground";
  } else if (dias < 0) {
    txt = `venceu há ${-dias} ${-dias === 1 ? "dia" : "dias"}`;
    cor = "border-destructive/45 bg-destructive/[0.12] text-destructive";
  } else if (dias === 0) {
    txt = "vence hoje"; cor = "border-destructive/45 bg-destructive/[0.12] text-destructive";
  } else if (dias <= 7) {
    txt = `vence em ${dias} ${dias === 1 ? "dia" : "dias"}`;
    cor = "border-warning/45 bg-warning/[0.12] text-warning";
  } else {
    txt = `vence em ${dias} dias`; cor = "border-border bg-secondary/40 text-muted-foreground";
  }
  return (
    <span className={`inline-flex shrink-0 items-center rounded-full border px-2.5 py-1 text-[11.5px] font-semibold ${cor}`}>
      {txt}
    </span>
  );
}

function Linha({
  x, tarjaFixa, aberta, aoAbrir, aoMarcar,
}: {
  x: Item; tarjaFixa?: string; aberta: boolean;
  aoAbrir: () => void;
  aoMarcar: (baixa: string | null, observacao: string | null) => Promise<void>;
}) {
  const [obs, setObs] = useState(x.observacao ?? "");
  const [salvando, setSalvando] = useState(false);
  useEffect(() => { setObs(x.observacao ?? ""); }, [x.observacao]);

  const marcar = async (baixa: string | null) => {
    setSalvando(true);
    try { await aoMarcar(baixa, obs.trim() || null); } finally { setSalvando(false); }
  };

  return (
    <div className="border-t border-border/50 first:border-t-0">
      <div
        onClick={aoAbrir}
        className="grid cursor-pointer gap-x-4 gap-y-2 px-4 py-3.5 transition-colors hover:bg-primary/[0.04] lg:grid-cols-[168px_104px_minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1fr)] lg:items-start"
      >
        <div><Tarja dias={x.dias} fixa={tarjaFixa} /></div>

        <div className="text-[12.5px] leading-tight">
          <div className="font-medium text-foreground">{br(x.prazo_entrega)}</div>
          <div className="text-muted-foreground">
            {x.data_aceite ? `aceite ${br(x.data_aceite)}` : "sem aceite"}
          </div>
        </div>

        <div className="min-w-0">
          <div className="font-mono text-[13px] text-primary">{x.processo}</div>
          <div className="mt-0.5 text-[12.4px] leading-snug text-muted-foreground">
            {x.partes || "partes não informadas"}
          </div>
          {x.observacao && (
            <div className="mt-1.5 flex items-start gap-1.5 rounded-md bg-secondary/50 px-2 py-1 text-[12px] text-foreground">
              <Pencil className="mt-[3px] h-3 w-3 shrink-0 text-muted-foreground" />
              <span className="whitespace-pre-wrap">{x.observacao}</span>
            </div>
          )}
        </div>

        <div className="min-w-0 text-[12.5px] leading-tight">
          <div className="font-medium text-foreground">{x.situacao_texto || "—"}</div>
          <div className="text-muted-foreground">{x.tarefa || "—"}</div>
        </div>

        <div className="min-w-0 text-[12.4px] leading-tight text-muted-foreground">
          <div>{x.orgao || "—"}</div>
          <div className="mt-0.5 opacity-80">
            {[x.fase, x.classe].filter(Boolean).join(" · ") || "—"}
          </div>
        </div>
      </div>

      {aberta && (
        <div className="flex flex-col gap-3 border-t border-border/40 bg-secondary/20 px-4 py-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-1 text-[12.5px] text-muted-foreground">Dar baixa:</span>
            {BAIXAS.map(([v, r]) => (
              <button
                key={v}
                disabled={salvando}
                onClick={() => marcar(v)}
                className={`rounded-lg border px-3 py-1.5 text-[12.5px] transition-colors disabled:opacity-50 ${
                  x.baixa === v
                    ? "border-success/50 bg-success/[0.14] text-success"
                    : "border-border/70 text-muted-foreground hover:border-border hover:text-foreground"
                }`}
              >
                {x.baixa === v && <Check className="mr-1 inline h-3 w-3" />}{r}
              </button>
            ))}
            {x.baixa && (
              <button
                disabled={salvando}
                onClick={() => marcar(null)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border/70 px-3 py-1.5 text-[12.5px] text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
              >
                <Undo2 className="h-3.5 w-3.5" /> desfazer
              </button>
            )}
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <label className="flex-1">
              <span className="mb-1 block text-[12.5px] text-muted-foreground">Observação (só sua)</span>
              <textarea
                value={obs}
                onChange={(e) => setObs(e.target.value)}
                rows={2}
                placeholder="ex.: pedi mais 5 dias · falta o PPP · conferir com o Drinho"
                className="w-full resize-y rounded-lg border border-border/50 bg-background/60 px-3 py-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20"
              />
            </label>
            <button
              disabled={salvando}
              onClick={() => marcar(x.baixa ?? null)}
              className="flex items-center gap-2 rounded-lg gradient-primary px-4 py-2.5 text-[13px] font-bold text-primary-foreground disabled:opacity-50"
            >
              {salvando ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
              Salvar
            </button>
          </div>

          <div className="text-[12px] text-muted-foreground">
            Dar baixa tira a linha do painel sem apagar nada — o registro do PJe
            continua igual, e “desfazer” devolve.
          </div>
        </div>
      )}
    </div>
  );
}

function Bloco({
  id, titulo, sub, itens, vazio, limite = 12, tarjaFixa, aberta, setAberta, marcar,
}: {
  id: string; titulo: string; sub: string; itens: Item[]; vazio: string;
  limite?: number; tarjaFixa?: string;
  aberta: number | null; setAberta: (n: number | null) => void;
  marcar: (id: number, baixa: string | null, obs: string | null) => Promise<void>;
}) {
  const [tudo, setTudo] = useState(false);
  const mostra = tudo ? itens : itens.slice(0, limite);
  return (
    <section id={id} className="scroll-mt-[130px]">
      <h2 className="mb-1.5 mt-[30px] flex items-baseline gap-2.5 text-[14.5px] font-semibold text-foreground">
        {titulo} <span className="font-normal text-muted-foreground">{itens.length}</span>
      </h2>
      <p className="mb-3.5 max-w-[86ch] text-[12.8px] text-muted-foreground">{sub}</p>
      {itens.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border/80 bg-card/35 px-5 py-6 text-[13px] text-muted-foreground">
          {vazio}
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-border/60 bg-card/40">
          {mostra.map((x) => (
            <Linha
              key={x.id_pericia} x={x} tarjaFixa={tarjaFixa}
              aberta={aberta === x.id_pericia}
              aoAbrir={() => setAberta(aberta === x.id_pericia ? null : x.id_pericia)}
              aoMarcar={(b, o) => marcar(x.id_pericia, b, o)}
            />
          ))}
          {itens.length > limite && (
            <button
              onClick={() => setTudo(!tudo)}
              className="w-full border-t border-border/50 py-2.5 text-[12.5px] text-primary transition-colors hover:bg-primary/[0.06]"
            >
              {tudo ? "mostrar menos" : `ver os outros ${itens.length - limite}`}
            </button>
          )}
        </div>
      )}
    </section>
  );
}

/* -------------------------------------------------------------------- tela */

export default function PericiasPainel() {
  const [p, setP] = useState<Perito | null>(null);
  const [d, setD] = useState<Painel | null>(null);
  const [erro, setErro] = useState(false);
  const [aberta, setAberta] = useState<number | null>(null);
  const [hz, setHz] = useState<[number, number]>([60, 15]);
  const [refazendo, setRefazendo] = useState(false);

  const carregar = useCallback((atras: number, frente: number) =>
    Promise.all([
      buscar("/api/pericias/perito").then((r) => (r.ok ? r.json() : Promise.reject())),
      buscar(`/api/pericias/painel?atras=${atras}&frente=${frente}`)
        .then((r) => (r.ok ? r.json() : Promise.reject())),
    ])
      .then(([perito, painel]) => { setP(perito); setD(painel); setErro(false); })
      .catch(() => setErro(true)), []);

  useEffect(() => { carregar(hz[0], hz[1]); }, [hz, carregar]);

  const marcar = async (id: number, baixa: string | null, observacao: string | null) => {
    const r = await buscar(`/api/pericias/pericia/${id}`, {
      method: "PUT", body: JSON.stringify({ baixa, observacao }),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      toast.error(j.msg || "Não consegui salvar.");
      return;
    }
    toast.success(baixa ? "Baixa registrada." : "Salvo.");
    setAberta(null);
    carregar(hz[0], hz[1]);
  };

  const refazer = async () => {
    setRefazendo(true);
    try {
      const r = await buscar("/api/pericias/painel/refazer", { method: "POST" });
      const j = await r.json();
      if (!r.ok) { toast.error(j.msg || "Não foi possível refazer."); return; }
      toast.success(`${j.pericias} perícias relidas.`);
      carregar(hz[0], hz[1]);
    } catch { toast.error("Erro de conexão."); }
    finally { setRefazendo(false); }
  };

  if (erro) {
    return (
      <CascaNova titulo="Perícias" descricao="Não consegui ler os seus dados." abas={ABAS_PERICIAS}>
        <div className="glass-card flex flex-col items-start gap-4 p-8">
          <div className="flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 text-warning" />
            <b className="text-foreground">Não consegui ler o seu painel agora.</b>
          </div>
          <p className="max-w-[60ch] text-[13px] text-muted-foreground">
            Isso é falha de leitura, não falta de cadastro — os seus dados continuam
            onde estavam.
          </p>
          <button
            onClick={() => { setErro(false); setP(null); setD(null); carregar(hz[0], hz[1]); }}
            className="rounded-xl gradient-primary px-5 py-2.5 text-sm font-bold text-primary-foreground"
          >
            Tentar de novo
          </button>
        </div>
      </CascaNova>
    );
  }

  if (!p || !d) {
    return (
      <CascaNova titulo="Painel" descricao="Carregando…" abas={ABAS_PERICIAS}>
        <div className="flex items-center gap-3 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> lendo o seu acervo
        </div>
      </CascaNova>
    );
  }

  if (!p.configurado || !d.tem_dados) {
    return (
      <CascaNova titulo="Perícias" descricao="Prazos e acervo do perito, lidos direto do PJe."
                 abas={ABAS_PERICIAS} rodapeAbas="PJe — sem IA">
        <Configurar p={p} temRetrato={d.tem_dados} />
      </CascaNova>
    );
  }

  const k = d.kpi;
  const env = d.ultimo_envio;
  const idade = env?.recebido_em
    ? Math.floor((Date.now() - new Date(env.recebido_em).getTime()) / 86400000) : null;
  const velho = idade !== null && idade >= 2;
  const comum = { aberta, setAberta, marcar };

  return (
    <CascaNova
      titulo="Painel"
      descricao="O que o PJe declara, sem dedução. Você dá baixa e anota o que quiser."
      abas={ABAS_PERICIAS}
      rodapeAbas="PJe — sem IA"
    >
      <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border border-border/60 bg-card/40 px-5 py-3 text-[12.8px]">
        <span><b className="text-foreground">{p.nome_tribunal}</b></span>
        <span className="text-muted-foreground">{ESP[p.especialidade ?? "contabil"]}</span>
        <span className="text-muted-foreground">{(p.tribunais ?? []).join(" · ")}</span>
        <span className={velho ? "text-warning" : "text-muted-foreground"}>
          retrato {idade === 0 ? "de hoje" : idade === 1 ? "de ontem" : `de ${idade} dias atrás`}
        </span>
        <span className="ml-auto flex items-center gap-3">
          <button onClick={refazer} disabled={refazendo}
            className="inline-flex items-center gap-1.5 text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50">
            <RefreshCw className={`h-3.5 w-3.5 ${refazendo ? "animate-spin" : ""}`} /> reler
          </button>
          <Link to="/pericias/pje" className="text-primary">atualizar do PJe</Link>
          <Link to="/pericias/cadastro" className="inline-flex items-center gap-1.5 text-primary">
            <Pencil className="h-3.5 w-3.5" /> editar
          </Link>
        </span>
      </div>

      {velho && (
        <div className="mb-5 flex flex-col gap-3 rounded-xl border border-warning/30 bg-warning/[0.07] px-5 py-4 sm:flex-row sm:items-center">
          <AlertTriangle className="h-5 w-5 shrink-0 text-warning" />
          <p className="flex-1 text-[13px] leading-snug text-foreground">
            <b>Este retrato tem {idade} dias.</b> O que você entregou depois disso
            ainda aparece aqui como pendente. Clique no favorito de novo para atualizar.
          </p>
          <Link to="/pericias/pje"
            className="shrink-0 rounded-lg border border-warning/40 bg-warning/[0.12] px-4 py-2 text-[12.8px] font-semibold text-warning hover:bg-warning/20">
            Atualizar
          </Link>
        </div>
      )}

      <div className="mb-3 flex flex-wrap items-center gap-2 text-[12.5px]">
        <span className="text-muted-foreground">Mostrar o que vence nos próximos</span>
        {HORIZONTES.map(([a, f, r]) => (
          <button
            key={r}
            onClick={() => setHz([a, f])}
            className={`rounded-lg border px-3 py-1.5 transition-colors ${
              hz[0] === a && hz[1] === f
                ? "border-primary/40 bg-primary/[0.13] text-foreground"
                : "border-border/70 text-muted-foreground hover:text-foreground"
            }`}
          >
            {r}
          </button>
        ))}
        {k.com_baixa > 0 && (
          <span className="ml-auto text-muted-foreground">{k.com_baixa} com baixa, fora do painel</span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi n={k.vencido} rotulo="Prazos vencidos" sub={`últimos ${d.horizonte.atras} dias, sem baixa`}
             cor="text-destructive" icone={<AlertTriangle className="h-[18px] w-[18px]" />} alvo="#b-vencido" />
        <Kpi n={k.correndo} rotulo="Prazos correndo" sub={`próximos ${d.horizonte.frente} dias`}
             cor="text-warning" icone={<Clock className="h-[18px] w-[18px]" />} alvo="#b-correndo" />
        <Kpi n={k.esclarecimentos} rotulo="Esclarecimentos" sub="o juízo pediu de volta"
             cor="text-primary" icone={<HelpCircle className="h-[18px] w-[18px]" />} alvo="#b-esclar" />
        <Kpi n={k.envelope} rotulo="Envelope aberto" sub="chegou algo no processo"
             cor="text-primary" icone={<Mail className="h-[18px] w-[18px]" />} alvo="#b-envelope" />
      </div>

      <Bloco id="b-vencido" titulo="Prazos vencidos" itens={d.vencido} {...comum}
        sub={`Data de entrega do PJe já passada, nos últimos ${d.horizonte.atras} dias, sem baixa sua. Se já entregou, clique na linha e marque “já fiz”.`}
        vazio="Nenhum prazo vencido neste período." />

      <Bloco id="b-correndo" titulo="Prazos correndo" itens={d.correndo} {...comum}
        sub={`Vencem nos próximos ${d.horizonte.frente} dias. A data é a que o tribunal fixou — nada é estimado aqui.`}
        vazio="Nada vencendo neste período." />

      <Bloco id="b-esclar" titulo="Esclarecimentos pedidos" itens={d.esclarecimentos} {...comum}
        sub="O PJe libera juntar esclarecimentos nestas perícias — é o tribunal dizendo que ainda espera algo de você, mesmo com o laudo já entregue."
        vazio="Nenhum pedido de esclarecimento em aberto." />

      <Bloco id="b-envelope" titulo="Envelope aberto" itens={d.envelope} tarjaFixa="algo chegou" {...comum}
        sub="Há expediente aberto no processo e o PJe não diz o que é. Abrir para ler registraria ciência e dispararia o prazo, então o sistema não abre — quem abre é você, no PJe. A data ao lado é a do laudo, não a do expediente."
        vazio="Nenhum expediente aberto." />

      <Bloco id="b-ciencia" titulo="Intimação sem ciência" itens={d.ciencia} tarjaFixa="sem ciência" {...comum}
        sub="Vem da aba Intimações do PJe, que é outra tela. Enquanto ninguém dá ciência o prazo não começa a correr. A data mostrada é a do laudo do processo, não a da intimação — o PJe não informa essa."
        vazio="Nenhuma intimação esperando ciência." />

      <Bloco id="b-sem-prazo" titulo="Sem data de entrega" itens={d.sem_prazo} {...comum}
        sub="Perícia aberta e o PJe não registrou data de entrega."
        vazio="Todas as perícias abertas têm data." />

      {k.fora > 0 && (
        <Bloco id="b-fora" titulo="Fora do período escolhido" itens={d.fora} limite={6} {...comum}
          sub={`Perícias abertas com data fora da janela atual — em geral coisa antiga que segue aberta no PJe. Aumente o período acima para trazer tudo.`}
          vazio="" />
      )}

      <div className="mt-8 grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-border/60 bg-card/40 px-5 py-4 text-[12.8px] leading-relaxed text-muted-foreground">
          <b className="text-foreground">O acervo inteiro.</b> {k.total} perícias
          neste retrato: {k.abertas} abertas, {k.entregue} com laudo entregue e{" "}
          {k.encerrada} canceladas ou redesignadas.
        </div>
        <div className="rounded-xl border border-border/60 bg-card/40 px-5 py-4 text-[12.8px] leading-relaxed text-muted-foreground">
          <b className="text-foreground">Dinheiro não vem do PJe.</b> Não existe campo
          de honorário, alvará ou pagamento nesta lista. Arbitramento e alvará são
          publicados, e vêm do diário — que ainda não está ligado.
        </div>
      </div>
    </CascaNova>
  );
}
