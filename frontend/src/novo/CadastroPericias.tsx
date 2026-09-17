// frontend/src/novo/CadastroPericias.tsx
//
// Cadastro do perito. Cinco campos, e cada um existe por causa de um erro
// concreto que o motor ja' cometeu — a microcópia abaixo de cada campo diz
// qual, porque quem preenche precisa entender por que aquilo importa.

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, Save } from "lucide-react";
import { toast } from "sonner";
import CascaNova from "./CascaNova";
import { buscar } from "./api";

const ESPECIALIDADES = [
  ["contabil", "Contábil"],
  ["medica", "Médica"],
  ["engenharia", "Engenharia"],
  ["outra", "Outra"],
] as const;

const TRTS = Array.from({ length: 24 }, (_, i) => `TRT${i + 1}`);

const UF: Record<string, string> = {
  TRT1: "RJ", TRT2: "SP capital", TRT3: "MG", TRT4: "RS", TRT5: "BA", TRT6: "PE",
  TRT7: "CE", TRT8: "PA/AP", TRT9: "PR", TRT10: "DF/TO", TRT11: "AM/RR", TRT12: "SC",
  TRT13: "PB", TRT14: "RO/AC", TRT15: "SP interior", TRT16: "MA", TRT17: "ES",
  TRT18: "GO", TRT19: "AL", TRT20: "SE", TRT21: "RN", TRT22: "PI", TRT23: "MT", TRT24: "MS",
};

const CAIXA = "glass-card p-[26px]";
const CAMPO =
  "w-full rounded-xl border border-border/50 bg-background/60 px-4 py-3 text-sm " +
  "text-foreground transition-all placeholder:text-muted-foreground " +
  "focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20";

function Dica({ children }: { children: React.ReactNode }) {
  return <p className="mt-1.5 text-[11.5px] leading-snug text-muted-foreground">{children}</p>;
}

function Pilula({
  ativo, onClick, children,
}: { ativo: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg border px-3 py-1.5 text-[13px] transition-colors ${
        ativo
          ? "border-primary/40 bg-primary/[0.13] text-foreground"
          : "border-border/70 text-muted-foreground hover:border-border hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

export default function CadastroPericias() {
  const navigate = useNavigate();

  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [jaConfigurado, setJaConfigurado] = useState(false);

  const [nome, setNome] = useState("");
  const [variacoes, setVariacoes] = useState("");
  const [genero, setGenero] = useState<"m" | "f">("m");
  const [especialidade, setEspecialidade] = useState("contabil");
  const [tribunais, setTribunais] = useState<string[]>([]);

  useEffect(() => {
    buscar("/api/pericias/perito")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.nome_tribunal) {
          setNome(d.nome_tribunal);
          setVariacoes((d.variacoes ?? []).join(", "));
          setGenero(d.genero === "f" ? "f" : "m");
          setEspecialidade(d.especialidade ?? "contabil");
          setTribunais(d.tribunais ?? []);
          setJaConfigurado(Boolean(d.configurado));
        }
      })
      .catch(() => {})
      .finally(() => setCarregando(false));
  }, []);

  const alternarTribunal = (t: string) =>
    setTribunais((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]));

  const salvar = async () => {
    if (nome.trim().length < 5) {
      toast.warning("Informe o nome completo como o tribunal escreve.");
      return;
    }
    if (tribunais.length === 0) {
      toast.warning("Escolha pelo menos um tribunal.");
      return;
    }
    setSalvando(true);
    try {
      const r = await buscar("/api/pericias/perito", {
        method: "PUT",
        body: JSON.stringify({
          nome_tribunal: nome,
          variacoes: variacoes.split(",").map((v) => v.trim()).filter(Boolean),
          genero,
          especialidade,
          tribunais,
        }),
      });
      const d = await r.json();
      if (!r.ok) {
        toast.error(d.msg || "Não foi possível salvar.");
        return;
      }
      toast.success("Cadastro salvo.");
      navigate("/pericias");
    } catch {
      toast.error("Erro de conexão.");
    } finally {
      setSalvando(false);
    }
  };

  if (carregando) {
    return (
      <CascaNova titulo="Quem é você no tribunal" descricao="Carregando…">
        <div className="flex items-center gap-3 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> lendo o cadastro
        </div>
      </CascaNova>
    );
  }

  return (
    <CascaNova
      titulo="Quem é você no tribunal"
      descricao="Cinco campos. Cada um existe porque sem ele o sistema erra de um jeito específico — está escrito ao lado de cada um."
    >
      <div className="grid gap-4 lg:grid-cols-[1.35fr_1fr]">
        <div className={`${CAIXA} flex flex-col gap-6`}>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              Nome completo, como o tribunal escreve
            </label>
            <input
              className={CAMPO}
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="LUCAS MACHADO DIESEL"
            />
            <Dica>A busca no diário é literal. É a chave de tudo.</Dica>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              Outras formas que aparecem <span className="font-normal text-muted-foreground">(opcional)</span>
            </label>
            <input
              className={CAMPO}
              value={variacoes}
              onChange={(e) => setVariacoes(e.target.value)}
              placeholder="LUCAS M. DIESEL, L. M. DIESEL"
            />
            <Dica>Separe por vírgula. Às vezes a vara abrevia — cada variação vira uma busca a mais.</Dica>
          </div>

          <div className="grid gap-6 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-foreground">
                Como o tribunal se refere a você
              </label>
              <div className="flex gap-2">
                <Pilula ativo={genero === "m"} onClick={() => setGenero("m")}>o perito</Pilula>
                <Pilula ativo={genero === "f"} onClick={() => setGenero("f")}>a perita</Pilula>
              </div>
              <Dica>
                Num despacho a vara escreveu “a perita” e o sistema cobrou um cálculo do
                perito errado. Este campo é o que evita isso.
              </Dica>
            </div>

            <div>
              <label className="mb-1.5 block text-sm font-medium text-foreground">Especialidade</label>
              <select
                className={CAMPO}
                value={especialidade}
                onChange={(e) => setEspecialidade(e.target.value)}
              >
                {ESPECIALIDADES.map(([v, r]) => (
                  <option key={v} value={v} className="bg-card">{r}</option>
                ))}
              </select>
              <Dica>
                Separa “honorários periciais contábeis” de “técnicos” ou “médicos” —
                que são de outro perito.
              </Dica>
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">Onde você atua</label>
            <div className="flex flex-wrap gap-2">
              {TRTS.map((t) => (
                <Pilula key={t} ativo={tribunais.includes(t)} onClick={() => alternarTribunal(t)}>
                  {t} <span className="opacity-60">{UF[t]}</span>
                </Pilula>
              ))}
            </div>
            <Dica>
              Chegou serviço do TRT3 por e-mail e o coletor só varria o TRT4. Marcar
              todos custa tempo de varredura — marque onde você realmente atua.
            </Dica>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={salvar}
              disabled={salvando}
              className="flex items-center gap-2 rounded-xl gradient-primary px-6 py-3 text-sm font-bold text-primary-foreground transition-all hover:shadow-lg hover:shadow-primary/25 disabled:opacity-50"
            >
              {salvando
                ? <><Loader2 className="h-4 w-4 animate-spin" /> Salvando…</>
                : <><Save className="h-4 w-4" /> {jaConfigurado ? "Salvar alterações" : "Salvar e continuar"}</>}
            </button>
            {jaConfigurado && (
              <button
                onClick={() => navigate("/pericias")}
                className="rounded-lg border border-border px-4 py-3 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                Cancelar
              </button>
            )}
          </div>
        </div>

        <div className={`${CAIXA} self-start`}>
          <div className="font-semibold text-foreground">O que não pedimos</div>
          <div className="mt-3 flex flex-col gap-2.5 text-[12.8px] text-muted-foreground">
            <div>Senha do PJe.</div>
            <div>Certificado digital.</div>
            <div>Acesso à sua caixa de e-mail.</div>
          </div>
          <p className="mt-5 border-t border-border/60 pt-4 text-[12.5px] leading-relaxed text-muted-foreground">
            Nada aqui é credencial. São dados que já estão públicos no diário — o
            sistema só precisa saber qual deles é você.
          </p>
        </div>
      </div>
    </CascaNova>
  );
}
