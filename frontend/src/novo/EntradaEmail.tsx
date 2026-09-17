// frontend/src/novo/EntradaEmail.tsx
//
// Entrada de trabalho particular por e-mail.
//
// Metade do dia do perito nao passa por tribunal nenhum: calculo contratado
// direto por advogado, sem nomeacao, sem numero no controle dele. Medido na
// agenda real: 12 de 27 itens de uma semana nao existem no PJe.
//
// Esta tela ainda NAO recebe e-mail sozinha. Ela existe para colar e-mails de
// verdade e ver o que o leitor entende — provar o leitor com o material dele
// antes de desviar correio de ninguem.

import { useEffect, useState } from "react";
import { AlertTriangle, Check, Inbox, Loader2, Trash2, Wand2, X } from "lucide-react";
import { toast } from "sonner";
import CascaNova from "./CascaNova";
import { ABAS_PERICIAS } from "./PericiasPainel";
import { buscar } from "./api";

interface Leitura {
  faixa: string;
  numero: string | null;
  onde_achou: string;
  justica: string;
  prazo: string | null;
  reclamante: string;
  reclamado: string;
  tarefas: string[];
  sinais: string[];
  contra: string[];
  outros_numeros: string[];
  no_acervo?: boolean;
}

interface Entrada extends Leitura {
  id: number;
  estado: string;
  remetente: string | null;
  assunto: string | null;
  corpo: string | null;
  anexos: string[];
  origem: string;
  recebido_em: string;
}

const FAIXA: Record<string, { rotulo: string; cor: string; diz: string }> = {
  entra: {
    rotulo: "Entra sozinho", cor: "border-success/45 bg-success/[0.12] text-success",
    diz: "Número trabalhista, prazo escrito e remetente identificado como advogado.",
  },
  confirmar: {
    rotulo: "Pede confirmação", cor: "border-warning/45 bg-warning/[0.12] text-warning",
    diz: "Tem número trabalhista, mas falta algo ou há sinal contrário.",
  },
  ignorar: {
    rotulo: "Descarta", cor: "border-border bg-secondary/50 text-muted-foreground",
    diz: "Sem número de processo, ou número de outra Justiça.",
  },
};

const CAMPO =
  "w-full rounded-xl border border-border/50 bg-background/60 px-4 py-3 text-sm " +
  "text-foreground transition-all placeholder:text-muted-foreground " +
  "focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20";

function br(iso: string | null) {
  if (!iso) return "—";
  const [a, m, d] = iso.split("-");
  return `${d}/${m}/${a}`;
}

function Resultado({ r }: { r: Leitura }) {
  const f = FAIXA[r.faixa] ?? FAIXA.ignorar;
  return (
    <div className="flex flex-col gap-4">
      <div>
        <span className={`inline-flex items-center rounded-full border px-3 py-1 text-[12.5px] font-semibold ${f.cor}`}>
          {f.rotulo}
        </span>
        <p className="mt-2 text-[12.8px] text-muted-foreground">{f.diz}</p>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-3 text-[12.8px]">
        <div>
          <div className="text-muted-foreground">Processo</div>
          <div className="font-mono text-[13px] text-foreground">{r.numero || "—"}</div>
          {r.numero && (
            <div className="text-[11.5px] text-muted-foreground">
              {r.justica || "justiça desconhecida"} · achado no {r.onde_achou}
            </div>
          )}
        </div>
        <div>
          <div className="text-muted-foreground">Prazo escrito</div>
          <div className="text-[13px] font-medium text-foreground">{br(r.prazo)}</div>
        </div>
        <div className="col-span-2">
          <div className="text-muted-foreground">Partes</div>
          <div className="text-foreground">
            {r.reclamante || r.reclamado ? `${r.reclamante || "?"} × ${r.reclamado || "?"}` : "—"}
          </div>
        </div>
      </div>

      {r.no_acervo && (
        <div className="rounded-lg border border-primary/30 bg-primary/[0.07] px-3 py-2 text-[12.5px] text-foreground">
          <b>Este processo já está no seu acervo do PJe.</b> Não é trabalho particular
          novo — é o mesmo processo chegando por outro caminho.
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        {r.sinais.map((s) => (
          <div key={s} className="flex items-start gap-2 text-[12.5px] text-foreground">
            <Check className="mt-[3px] h-3.5 w-3.5 shrink-0 text-success" /> {s}
          </div>
        ))}
        {r.contra.map((s) => (
          <div key={s} className="flex items-start gap-2 text-[12.5px] text-warning">
            <AlertTriangle className="mt-[3px] h-3.5 w-3.5 shrink-0" /> {s}
          </div>
        ))}
        {r.sinais.length === 0 && r.contra.length === 0 && (
          <div className="text-[12.5px] text-muted-foreground">Nenhum sinal encontrado.</div>
        )}
      </div>
    </div>
  );
}

function LinhaFila({ e, aoDecidir }: { e: Entrada; aoDecidir: (estado: string) => void }) {
  const [abrir, setAbrir] = useState(false);
  const f = FAIXA[e.faixa] ?? FAIXA.ignorar;
  return (
    <div className="border-t border-border/50 first:border-t-0">
      <div className="grid gap-x-4 gap-y-2 px-4 py-3.5 lg:grid-cols-[150px_minmax(0,1.4fr)_120px_minmax(0,1fr)_auto] lg:items-start">
        <span className={`inline-flex h-fit w-fit items-center rounded-full border px-2.5 py-1 text-[11.5px] font-semibold ${f.cor}`}>
          {f.rotulo}
        </span>

        <div className="min-w-0">
          <div className="font-mono text-[13px] text-primary">{e.numero || "sem número"}</div>
          <div className="mt-0.5 truncate text-[12.4px] text-muted-foreground">
            {e.reclamante || e.reclamado ? `${e.reclamante || "?"} × ${e.reclamado || "?"}` : (e.assunto || "—")}
          </div>
        </div>

        <div className="text-[12.5px]">
          <div className="font-medium text-foreground">{br(e.prazo)}</div>
          <div className="text-muted-foreground">{e.prazo ? "prazo do advogado" : "sem prazo"}</div>
        </div>

        <div className="min-w-0 text-[12.4px] text-muted-foreground">
          <div className="truncate">{e.remetente || "—"}</div>
          {e.anexos.length > 0 && <div className="truncate opacity-80">{e.anexos.join(", ")}</div>}
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          <button onClick={() => setAbrir(!abrir)}
            className="rounded-lg border border-border/70 px-2.5 py-1.5 text-[12px] text-muted-foreground hover:text-foreground">
            {abrir ? "fechar" : "ver"}
          </button>
          {e.estado === "novo" ? (
            <>
              <button onClick={() => aoDecidir("aceito")} title="Aceitar"
                className="rounded-lg border border-success/40 bg-success/[0.12] px-2.5 py-1.5 text-success">
                <Check className="h-3.5 w-3.5" />
              </button>
              <button onClick={() => aoDecidir("descartado")} title="Descartar"
                className="rounded-lg border border-border/70 px-2.5 py-1.5 text-muted-foreground hover:text-foreground">
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </>
          ) : (
            <button onClick={() => aoDecidir("novo")}
              className="rounded-lg border border-border/70 px-2.5 py-1.5 text-[12px] text-muted-foreground hover:text-foreground">
              {e.estado === "aceito" ? "aceito" : "descartado"} · desfazer
            </button>
          )}
        </div>
      </div>

      {abrir && (
        <div className="grid gap-4 border-t border-border/40 bg-secondary/20 px-4 py-4 lg:grid-cols-2">
          <div><Resultado r={e} /></div>
          <div>
            <div className="mb-1.5 text-[12.5px] font-medium text-foreground">O e-mail como chegou</div>
            <div className="max-h-[280px] overflow-auto rounded-lg border border-border/50 bg-background/50 p-3 text-[12.3px] leading-relaxed text-muted-foreground">
              <div className="text-foreground">{e.assunto || "(sem assunto)"}</div>
              <div className="mb-2 text-[11.5px]">{e.remetente}</div>
              <div className="whitespace-pre-wrap">
                {e.corpo || "(corpo já apagado — guardamos por 30 dias)"}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function EntradaEmail() {
  const [remetente, setRemetente] = useState("");
  const [assunto, setAssunto] = useState("");
  const [corpo, setCorpo] = useState("");
  const [anexos, setAnexos] = useState("");
  const [r, setR] = useState<Leitura | null>(null);
  const [lendo, setLendo] = useState(false);
  const [fila, setFila] = useState<Entrada[] | null>(null);
  const [cont, setCont] = useState<Record<string, number>>({});

  const carregar = () =>
    buscar("/api/pericias/entrada")
      .then((x) => (x.ok ? x.json() : { entradas: [], contagem: {} }))
      .then((d) => { setFila(d.entradas ?? []); setCont(d.contagem ?? {}); })
      .catch(() => setFila([]));

  useEffect(() => { carregar(); }, []);

  const pedido = () => ({
    remetente, assunto, corpo,
    anexos: anexos.split(",").map((s) => s.trim()).filter(Boolean),
  });

  const acao = async (url: string, guardar: boolean) => {
    if (!assunto.trim() && !corpo.trim()) {
      toast.warning("Cole o e-mail antes.");
      return;
    }
    setLendo(true);
    try {
      const x = await buscar(url, { method: "POST", body: JSON.stringify(pedido()) });
      const d = await x.json();
      if (!x.ok) { toast.error(d.msg || "Não consegui ler."); return; }
      setR(d);
      if (guardar) {
        toast.success(d.repetido ? "Já tinha chegado — não dupliquei." : "Guardado na fila.");
        carregar();
      }
    } catch { toast.error("Erro de conexão."); }
    finally { setLendo(false); }
  };

  const decidir = async (id: number, estado: string) => {
    const x = await buscar(`/api/pericias/entrada/${id}`, {
      method: "PUT", body: JSON.stringify({ estado }),
    });
    if (!x.ok) { toast.error("Não consegui salvar."); return; }
    carregar();
  };

  return (
    <CascaNova
      titulo="Entrada por e-mail"
      descricao="O trabalho que o advogado manda direto, e que nenhum tribunal conhece."
      abas={ABAS_PERICIAS}
      rodapeAbas="leitura por regra fixa — sem IA"
    >
      <div className="mb-5 rounded-xl border border-primary/25 bg-primary/[0.05] px-5 py-4 text-[12.8px] leading-relaxed text-foreground">
        <b>Ainda não recebemos e-mail sozinhos.</b> Esta tela existe para você colar
        e-mails de verdade e conferir o que o sistema entende deles. Quando a leitura
        estiver acertando no material do Lucas, aí sim criamos o endereço e a regra
        de encaminhamento — provar antes de desviar correio.
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.25fr_1fr]">
        <div className="glass-card flex flex-col gap-4 p-[26px]">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">De</label>
            <input className={CAMPO} value={remetente} onChange={(e) => setRemetente(e.target.value)}
              placeholder="Irineu Gehlen &lt;irineu@gehlen.adv.br&gt;" />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">Assunto</label>
            <input className={CAMPO} value={assunto} onChange={(e) => setAssunto(e.target.value)}
              placeholder="FULANO x EMPRESA - IMPUGNAÇÃO - 0011059-25.2023.5.03.0142 - PZ 15/09/26" />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">Corpo</label>
            <textarea className={`${CAMPO} min-h-[160px] resize-y font-mono text-[12.5px]`}
              value={corpo} onChange={(e) => setCorpo(e.target.value)}
              placeholder="Cole aqui o texto da mensagem, com assinatura e tudo." />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              Nomes dos anexos <span className="font-normal text-muted-foreground">(opcional)</span>
            </label>
            <input className={CAMPO} value={anexos} onChange={(e) => setAnexos(e.target.value)}
              placeholder="0011059-25.2023.5.03.0142 - cálculos.pdf" />
            <p className="mt-1.5 text-[11.5px] text-muted-foreground">
              Só o nome. O conteúdo do anexo nunca é guardado — e às vezes o número do
              processo só aparece aí.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <button onClick={() => acao("/api/pericias/entrada/testar", false)} disabled={lendo}
              className="flex items-center gap-2 rounded-xl border border-border px-5 py-2.5 text-sm font-medium text-foreground disabled:opacity-50">
              {lendo ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
              Ler sem guardar
            </button>
            <button onClick={() => acao("/api/pericias/entrada", true)} disabled={lendo}
              className="flex items-center gap-2 rounded-xl gradient-primary px-5 py-2.5 text-sm font-bold text-primary-foreground disabled:opacity-50">
              <Inbox className="h-4 w-4" /> Ler e guardar na fila
            </button>
            {(assunto || corpo || remetente || anexos) && (
              <button onClick={() => { setRemetente(""); setAssunto(""); setCorpo(""); setAnexos(""); setR(null); }}
                className="flex items-center gap-1.5 text-[12.5px] text-muted-foreground hover:text-foreground">
                <X className="h-3.5 w-3.5" /> limpar
              </button>
            )}
          </div>
        </div>

        <div className="glass-card self-start p-[26px]">
          <div className="mb-3.5 font-semibold text-foreground">O que o sistema entendeu</div>
          {r ? <Resultado r={r} /> : (
            <div className="flex flex-col gap-3 text-[12.6px] leading-relaxed text-muted-foreground">
              <p>Cole um e-mail e clique em ler.</p>
              <p>
                O leitor não tenta entender o formato — cada advogado escreve de um
                jeito. Ele procura três coisas em qualquer lugar da mensagem: um
                número CNJ, uma data marcada como prazo, e um remetente que se
                identifica como advogado.
              </p>
              <p>
                O número, sozinho, já é quase todo o filtro: ninguém manda newsletter
                com um número CNJ dentro. E o 13º dígito diz a Justiça — <b>5</b> é
                Trabalho.
              </p>
            </div>
          )}
        </div>
      </div>

      <section className="mt-8">
        <h2 className="mb-1.5 flex items-baseline gap-2.5 text-[14.5px] font-semibold text-foreground">
          A fila <span className="font-normal text-muted-foreground">{cont.total ?? 0}</span>
        </h2>
        <p className="mb-3.5 text-[12.8px] text-muted-foreground">
          {cont.entra ?? 0} entrariam sozinhos · {cont.confirmar ?? 0} pedem confirmação ·{" "}
          {cont.ignorar ?? 0} seriam descartados. Nada some sem rastro: o descarte fica
          registrado, para você poder ver se o sistema comeu algo que não devia.
        </p>

        {fila === null ? (
          <div className="flex items-center gap-3 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> lendo
          </div>
        ) : fila.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border/80 bg-card/35 px-5 py-6 text-[13px] text-muted-foreground">
            Nada na fila ainda. Cole um e-mail acima e clique em “ler e guardar”.
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-border/60 bg-card/40">
            {fila.map((e) => (
              <LinhaFila key={e.id} e={e} aoDecidir={(estado) => decidir(e.id, estado)} />
            ))}
          </div>
        )}
      </section>
    </CascaNova>
  );
}
