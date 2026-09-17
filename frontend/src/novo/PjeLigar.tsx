// frontend/src/novo/PjeLigar.tsx
//
// Passo 3 da configuracao: o favorito que le' o PJe.
//
// A tela mostra o codigo INTEIRO, nao um resumo. E' o unico jeito honesto de
// pedir que alguem instale algo que vai rodar dentro da sessao do tribunal
// dele: quem quiser conferir, confere; quem nao quiser, pelo menos ve' que nao
// esta' escondido.

import { useEffect, useRef, useState } from "react";
import {
  Check, Copy, Download, FileUp, Loader2, RefreshCw, Upload,
} from "lucide-react";
import { toast } from "sonner";
import CascaNova from "./CascaNova";
import { ABAS_PERICIAS } from "./PericiasPainel";
import { buscar } from "./api";
import { montarFonte, montarHref } from "./bookmarklet";

interface Envio {
  id: number;
  tribunal: string;
  perito_pje: string;
  via: string;
  bytes: number;
  vivas: number;
  finalizadas: number;
  arquivadas: number;
  intimacoes: number;
  recebido_em: string | null;
}

const CAIXA = "glass-card p-[26px]";

function Passo({ n, titulo, children }: { n: number; titulo: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3.5">
      <span className="mt-[2px] flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-primary/40 bg-primary/[0.12] text-[12px] font-bold text-primary">
        {n}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-foreground">{titulo}</div>
        <div className="mt-1 text-[12.8px] leading-relaxed text-muted-foreground">{children}</div>
      </div>
    </div>
  );
}

function quando(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function PjeLigar() {
  const [token, setToken] = useState("");
  const [gerando, setGerando] = useState(false);
  const [copiado, setCopiado] = useState(false);
  const [envios, setEnvios] = useState<Envio[] | null>(null);
  const [subindo, setSubindo] = useState(false);
  const linkRef = useRef<HTMLAnchorElement>(null);
  const arquivoRef = useRef<HTMLInputElement>(null);

  const destino = `${window.location.origin}/api/pericias/pje`;
  const fonte = token ? montarFonte(token, destino) : "";

  const lerEnvios = () =>
    buscar("/api/pericias/pje/envios")
      .then((r) => (r.ok ? r.json() : { envios: [] }))
      .then((d) => setEnvios(d.envios ?? []))
      .catch(() => setEnvios([]));

  useEffect(() => { lerEnvios(); }, []);

  // O React recusa href="javascript:..." escrito no JSX. Aqui o valor entra
  // pelo DOM, que e' o unico jeito de o favorito poder ser ARRASTADO para a
  // barra — e arrastar e' muito mais facil do que criar favorito na mao.
  useEffect(() => {
    if (linkRef.current && token) {
      linkRef.current.setAttribute("href", montarHref(token, destino));
    }
  }, [token, destino]);

  const gerar = async () => {
    setGerando(true);
    try {
      const r = await buscar("/api/pericias/perito/token", { method: "POST" });
      const d = await r.json();
      if (!r.ok) {
        toast.error(d.msg || "Não foi possível gerar.");
        return;
      }
      setToken(d.token);
      toast.success("Favorito gerado. Arraste para a barra do navegador.");
    } catch {
      toast.error("Erro de conexão.");
    } finally {
      setGerando(false);
    }
  };

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(montarHref(token, destino));
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      toast.error("O navegador não deixou copiar. Selecione o texto e copie à mão.");
    }
  };

  const subirArquivo = async (f: File) => {
    setSubindo(true);
    try {
      const texto = await f.text();
      const r = await buscar("/api/pericias/pje/arquivo", { method: "POST", body: texto });
      const d = await r.json();
      if (!r.ok) {
        toast.error(d.msg || "Arquivo recusado.");
        return;
      }
      toast.success(`Recebido: ${d.vivas} perícias em andamento.`);
      lerEnvios();
    } catch {
      toast.error("Não consegui ler o arquivo.");
    } finally {
      setSubindo(false);
      if (arquivoRef.current) arquivoRef.current.value = "";
    }
  };

  return (
    <CascaNova
      titulo="Ligar o PJe"
      descricao="O PJe é a única fonte que declara a data de entrega. Sem ele o painel mostra os processos, mas nenhum prazo."
      abas={ABAS_PERICIAS}
      rodapeAbas="PJe · DJEN · JTe · DataJud — sem IA"
    >
      <div className="grid gap-4 lg:grid-cols-[1.45fr_1fr]">
        {/* ------------------------------------------------------ instalar */}
        <div className={`${CAIXA} flex flex-col gap-6`}>
          <div className="flex flex-col gap-5">
            <Passo n={1} titulo="Gere o seu favorito">
              Ele nasce com um código só seu. Gerar de novo invalida o anterior —
              é assim que se revoga um favorito perdido.
            </Passo>
            <Passo n={2} titulo="Arraste o botão para a barra de favoritos">
              Se a barra estiver escondida, <b>Ctrl+Shift+B</b> mostra. Também dá
              para copiar o código e criar o favorito à mão, colando no campo de
              endereço.
            </Passo>
            <Passo n={3} titulo="Abra o PJe no perfil Perito e clique no favorito">
              Ele lê a mesma lista que a tela já mostra, e manda para cá. Aparece
              uma caixinha no canto contando o que encontrou.
            </Passo>
          </div>

          {!token ? (
            <button
              onClick={gerar}
              disabled={gerando}
              className="flex w-fit items-center gap-2 rounded-xl gradient-primary px-6 py-3 text-sm font-bold text-primary-foreground transition-all hover:shadow-lg hover:shadow-primary/25 disabled:opacity-50"
            >
              {gerando
                ? <><Loader2 className="h-4 w-4 animate-spin" /> Gerando…</>
                : <><Download className="h-4 w-4" /> Gerar meu favorito</>}
            </button>
          ) : (
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-center gap-3 rounded-xl border border-primary/30 bg-primary/[0.07] px-5 py-4">
                {/* eslint-disable-next-line jsx-a11y/anchor-is-valid */}
                <a
                  ref={linkRef}
                  draggable
                  onClick={(e) => {
                    e.preventDefault();
                    toast.info("Não clique aqui — arraste para a barra de favoritos.");
                  }}
                  className="cursor-grab rounded-lg bg-primary px-4 py-2 text-sm font-bold text-primary-foreground active:cursor-grabbing"
                >
                  Ler o PJe
                </a>
                <span className="text-[12.5px] text-muted-foreground">
                  ← arraste este botão para a barra de favoritos
                </span>
                <button
                  onClick={copiar}
                  className="ml-auto flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-[12.5px] text-muted-foreground transition-colors hover:text-foreground"
                >
                  {copiado ? <Check className="h-3.5 w-3.5 text-success" /> : <Copy className="h-3.5 w-3.5" />}
                  {copiado ? "Copiado" : "Copiar código"}
                </button>
                <button
                  onClick={gerar}
                  className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-[12.5px] text-muted-foreground transition-colors hover:text-foreground"
                >
                  <RefreshCw className="h-3.5 w-3.5" /> Gerar outro
                </button>
              </div>

              <details className="rounded-xl border border-border/60 bg-card/40">
                <summary className="cursor-pointer px-5 py-3 text-[13px] font-medium text-foreground">
                  Ver o código inteiro que vai ser instalado
                </summary>
                <pre className="max-h-[340px] overflow-auto border-t border-border/60 px-5 py-4 text-[11.5px] leading-[1.55] text-muted-foreground">
{fonte}
                </pre>
              </details>
            </div>
          )}
        </div>

        {/* -------------------------------------------------------- confianca */}
        <div className={`${CAIXA} self-start`}>
          <div className="font-semibold text-foreground">Por que isto é seguro</div>
          <div className="mt-3.5 flex flex-col gap-3.5 text-[12.6px] leading-relaxed text-muted-foreground">
            <div>
              <b className="text-foreground">Não pega a sua senha.</b> O cookie da
              sessão do PJe é <i>HttpOnly</i>: nenhum código de página consegue
              lê-lo, nem este. Não é promessa — é o navegador que impede.
            </div>
            <div>
              <b className="text-foreground">Só lê.</b> Faz as mesmas quatro
              consultas que a tela do PJe já faz sozinha ao carregar. Não abre
              expediente, não dá ciência, não peticiona, não assina.
            </div>
            <div>
              <b className="text-foreground">Não muda sozinho.</b> Favorito é
              texto congelado: o código fica no seu navegador do jeito que você
              instalou. Se um dia mudarmos, você instala de novo — ou não.
            </div>
            <div>
              <b className="text-foreground">O código é de mão única.</b> Com ele
              só se consegue <i>mandar</i> dados para a sua conta. Não lê nada,
              não entra em lugar nenhum. Se vazar, o pior caso é alguém sujar o
              seu painel — e "Gerar outro" resolve.
            </div>
          </div>
          <p className="mt-5 border-t border-border/60 pt-4 text-[12.4px] leading-relaxed text-muted-foreground">
            Estamos pedindo ao CNJ acesso oficial pela PDPJ. Quando sair, o
            favorito deixa de ser necessário e some daqui.
          </p>
        </div>
      </div>

      {/* ------------------------------------------------------------- log */}
      <section className="mt-6">
        <h2 className="mb-1.5 text-[14.5px] font-semibold text-foreground">O que já chegou</h2>
        <p className="mb-3.5 text-[12.8px] text-muted-foreground">
          Todo envio fica registrado. Se aparecer aqui algo que você não mandou,
          gere outro favorito — o anterior para de funcionar na hora.
        </p>

        {envios === null ? (
          <div className="flex items-center gap-3 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> lendo
          </div>
        ) : envios.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border/80 bg-card/35 px-5 py-6 text-[13px] text-muted-foreground">
            Nada ainda. Depois do primeiro clique no favorito, cada leitura aparece aqui.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-border/60">
            <table className="w-full min-w-[620px] text-[12.8px]">
              <thead className="bg-card/60 text-muted-foreground">
                <tr>
                  {["Quando", "Tribunal", "Perito", "Em andamento", "Finalizadas", "Arquivadas", "Intimações", "Via"].map((h) => (
                    <th key={h} className="px-4 py-2.5 text-left font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {envios.map((e) => (
                  <tr key={e.id} className="border-t border-border/50">
                    <td className="px-4 py-2.5 text-foreground">{quando(e.recebido_em)}</td>
                    <td className="px-4 py-2.5">{e.tribunal || "—"}</td>
                    <td className="px-4 py-2.5">{e.perito_pje || "—"}</td>
                    <td className="px-4 py-2.5 text-foreground">{e.vivas}</td>
                    <td className="px-4 py-2.5">{e.finalizadas}</td>
                    <td className="px-4 py-2.5">{e.arquivadas}</td>
                    <td className="px-4 py-2.5">{e.intimacoes}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">{e.via}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-border/60 bg-card/40 px-5 py-4">
          <FileUp className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="text-[12.6px] text-muted-foreground">
            Se o PJe bloquear o envio direto, o favorito baixa um arquivo. Suba ele aqui.
          </span>
          <input
            ref={arquivoRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) subirArquivo(f); }}
          />
          <button
            onClick={() => arquivoRef.current?.click()}
            disabled={subindo}
            className="ml-auto flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-[12.5px] text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
          >
            {subindo ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
            Escolher arquivo
          </button>
        </div>
      </section>
    </CascaNova>
  );
}
