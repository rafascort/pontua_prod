// frontend/src/novo/HoleriteNovo.tsx
//
// Extrator de Holerite no layout novo.
//
// Mesmas chamadas da tela atual:
//   /api/payroll/analyze  ->  poll  ->  modal de verbas
//   /api/payroll/process  ->  poll  ->  /api/download/<id>

import { useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, FileSpreadsheet, FileText, Loader2, Play, X } from "lucide-react";
import { toast } from "sonner";
import { useUserPlan } from "@/hooks/useUserPlan";
import CascaNova from "./CascaNova";
import { AreaUpload, CartaoPlano, ComoFunciona, ModalSaldo, Progresso } from "./Pecas";
import { baixar, buscar, contarPaginas } from "./api";

interface DadosAnalise {
  nomes: string[];
  verbas: string[];
  pdf_path: string;
  pages: string;
}

/* ------------------------------------------------------------ modal verbas */

function ModalVerbas({
  dados,
  aoFechar,
  aoConfirmar,
}: {
  dados: DadosAnalise;
  aoFechar: () => void;
  aoConfirmar: (taskId: string) => void;
}) {
  const [escolhidas, setEscolhidas] = useState<string[]>([]);
  const [carregando, setCarregando] = useState(false);

  const alternar = (v: string) =>
    setEscolhidas((prev) => (prev.includes(v) ? prev.filter((x) => x !== v) : [...prev, v]));

  const confirmar = async () => {
    if (escolhidas.length === 0) {
      toast.warning("Selecione pelo menos uma verba.");
      return;
    }
    setCarregando(true);
    try {
      const res = await buscar("/api/payroll/process", {
        method: "POST",
        body: JSON.stringify({
          pdf_path: dados.pdf_path,
          pages: dados.pages,
          selected_verbas: escolhidas,
          known_names: dados.nomes ?? [],
        }),
      });
      const d = await res.json();
      if (res.ok && d.task_id) {
        toast.success("Processamento iniciado!");
        aoConfirmar(d.task_id);
      } else {
        toast.error(d.error || "Erro ao iniciar processamento.");
      }
    } catch {
      toast.error("Erro de conexão.");
    } finally {
      setCarregando(false);
    }
  };

  return (
    <AnimatePresence>
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
          className="glass-card relative flex max-h-[90vh] w-full max-w-3xl flex-col"
        >
          <div className="flex shrink-0 items-center justify-between border-b border-border/50 p-6">
            <div>
              <h3 className="text-lg font-bold text-foreground">Escolher as verbas</h3>
              {dados.nomes.length > 0 && (
                <p className="mt-1 text-sm text-muted-foreground">
                  Funcionários: {dados.nomes.join(", ")}
                </p>
              )}
            </div>
            <button
              onClick={aoFechar}
              className="rounded-lg p-2 text-muted-foreground transition-all hover:bg-secondary/60 hover:text-foreground"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="flex flex-1 flex-col overflow-hidden p-6">
            <div className="mb-4 flex items-center justify-between">
              <h4 className="text-sm font-semibold text-foreground">
                Selecionadas: {escolhidas.length} de {dados.verbas.length}
              </h4>
              <div className="flex gap-2">
                <button
                  onClick={() => setEscolhidas([...dados.verbas])}
                  className="rounded-lg bg-primary/10 px-3 py-1.5 text-xs text-primary transition-all hover:bg-primary/20"
                >
                  Todas
                </button>
                <button
                  onClick={() => setEscolhidas([])}
                  className="rounded-lg bg-secondary/60 px-3 py-1.5 text-xs text-muted-foreground transition-all hover:bg-secondary"
                >
                  Nenhuma
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
              {dados.verbas.map((verba, i) => {
                const marcada = escolhidas.includes(verba);
                return (
                  <button
                    key={i}
                    onClick={() => alternar(verba)}
                    className={`flex items-center gap-3 rounded-lg border p-3 text-left text-sm transition-all ${
                      marcada
                        ? "border-primary/50 bg-primary/10 text-foreground"
                        : "border-border/40 bg-secondary/30 text-muted-foreground hover:border-border hover:text-foreground"
                    }`}
                  >
                    <div
                      className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-all ${
                        marcada ? "border-primary bg-primary" : "border-border/60"
                      }`}
                    >
                      {marcada && <Check className="h-3 w-3 text-primary-foreground" />}
                    </div>
                    <span className="truncate">{verba}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex shrink-0 gap-3 border-t border-border/50 p-6">
            <button
              onClick={aoFechar}
              className="flex-1 rounded-lg border border-border py-3 text-sm font-medium text-foreground transition-all hover:bg-surface-hover"
            >
              Cancelar
            </button>
            <button
              onClick={confirmar}
              disabled={carregando || escolhidas.length === 0}
              className="flex flex-1 items-center justify-center gap-2 rounded-xl gradient-primary py-3 text-sm font-bold text-primary-foreground transition-all hover:shadow-lg hover:shadow-primary/25 disabled:opacity-50"
            >
              {carregando
                ? <><Loader2 className="h-4 w-4 animate-spin" /> Iniciando...</>
                : <><Play className="h-4 w-4" /> Confirmar e gerar Excel</>}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

/* -------------------------------------------------------------------- tela */

export default function HoleriteNovo({ aoVoltarAntigo }: { aoVoltarAntigo?: () => void }) {
  const { plan, canUseExtras, refreshUser } = useUserPlan();

  const [arquivo, setArquivo] = useState<File | null>(null);
  const [intervalo, setIntervalo] = useState("");

  const [analisando, setAnalisando] = useState(false);
  const [progAnalise, setProgAnalise] = useState({ current: 0, total: 0, message: "Analisando..." });

  const [analise, setAnalise] = useState<DadosAnalise | null>(null);
  const [mostrarVerbas, setMostrarVerbas] = useState(false);

  const [processando, setProcessando] = useState(false);
  const [progProcesso, setProgProcesso] = useState({ current: 0, total: 0, message: "Processando..." });

  const [saldoCurto, setSaldoCurto] = useState<{ pedidas: number; disponiveis: number } | null>(null);

  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const vaiConsumir = useMemo(() => contarPaginas(intervalo), [intervalo]);
  const ocupado = analisando || processando;
  const semSaldo = !canUseExtras && plan.pageBalance <= 0;
  const temSaldo = canUseExtras || plan.pageBalance >= vaiConsumir;
  const progresso = analisando ? progAnalise : progProcesso;

  const acompanhar = (
    taskId: string,
    aoTerminar: (d: { filename?: string; result?: DadosAnalise }) => void,
    setProg: (p: { current: number; total: number; message: string }) => void
  ) => {
    if (timer.current) clearInterval(timer.current);
    timer.current = setInterval(async () => {
      try {
        const res = await buscar(`/api/progress/${taskId}`);
        const d = await res.json();
        if (d.current_step !== undefined) {
          setProg({
            current: d.current_step,
            total: d.total_steps || 1,
            message: d.message || "Processando...",
          });
        }
        if (d.status === "completed") {
          if (timer.current) clearInterval(timer.current);
          aoTerminar(d);
        } else if (d.status === "error" || d.status === "failed") {
          if (timer.current) clearInterval(timer.current);
          toast.error(d.error || "Erro no processamento.");
          setAnalisando(false);
          setProcessando(false);
        }
      } catch { /* rede instavel, continua tentando */ }
    }, 2000);
  };

  const comecar = async () => {
    if (!arquivo || !intervalo.trim()) {
      toast.warning("Selecione um PDF e informe as páginas.");
      return;
    }
    if (semSaldo || !temSaldo) {
      setSaldoCurto({ pedidas: vaiConsumir, disponiveis: plan.pageBalance });
      return;
    }

    setAnalisando(true);
    setProgAnalise({ current: 0, total: 1, message: "Enviando PDF para análise..." });

    const form = new FormData();
    form.append("pdf_file", arquivo);
    form.append("pages", intervalo);

    try {
      const res = await buscar("/api/payroll/analyze", { method: "POST", body: form });
      const d = await res.json();
      if (d.task_id) {
        acompanhar(d.task_id, (r) => {
          setAnalisando(false);
          if (r.result) {
            setAnalise({ ...r.result, pages: intervalo });
            setMostrarVerbas(true);
          } else {
            toast.error("Análise não retornou dados.");
          }
        }, setProgAnalise);
      } else {
        setAnalisando(false);
        toast.error("Falha ao iniciar análise.");
      }
    } catch {
      setAnalisando(false);
      toast.error("Erro de conexão.");
    }
  };

  const verbasConfirmadas = (taskId: string) => {
    setMostrarVerbas(false);
    setProcessando(true);
    setProgProcesso({ current: 0, total: 1, message: "Processando holerite..." });
    acompanhar(taskId, async (d) => {
      setProcessando(false);
      toast.success("Holerite gerado com sucesso!");
      const res = await buscar(`/api/download/${taskId}`);
      baixar(await res.blob(), d.filename || `Folha_${taskId}.xlsx`);
      await refreshUser();
    }, setProgProcesso);
  };

  const caixa = "glass-card p-[26px]";

  return (
    <CascaNova
      titulo="Extrator de Holerite"
      descricao="Lê contracheques em PDF e monta um Excel com uma aba por funcionário e uma coluna por verba."
      aoVoltarAntigo={aoVoltarAntigo}
    >
      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-4">
          <div className={caixa}>
            <AreaUpload
              arquivo={arquivo}
              aoEscolher={setArquivo}
              desabilitado={ocupado}
              icone={<FileSpreadsheet className="h-[22px] w-[22px]" />}
            />
          </div>

          <div className={caixa}>
            <label className="mb-2 block text-sm font-medium text-foreground">
              Páginas a processar
            </label>
            <input
              type="text"
              value={intervalo}
              onChange={(e) => setIntervalo(e.target.value)}
              placeholder="Ex: 1-5, 8, 10-12"
              disabled={ocupado}
              className="w-full rounded-xl border border-border/50 bg-background/60 px-4 py-3 text-sm text-foreground transition-all placeholder:text-muted-foreground focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20 disabled:opacity-50"
            />
          </div>

          <div className="flex justify-end">
            <button
              onClick={comecar}
              disabled={ocupado || !arquivo || !intervalo.trim() || semSaldo}
              className="flex items-center gap-2 rounded-xl gradient-primary px-8 py-3 text-sm font-bold text-primary-foreground transition-all hover:shadow-lg hover:shadow-primary/25 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {ocupado
                ? <><Loader2 className="h-5 w-5 animate-spin" /> {progresso.message}</>
                : <><FileText className="h-5 w-5" /> Identificar itens</>}
            </button>
          </div>
        </div>

        <div className="space-y-4 lg:sticky lg:top-[118px] lg:self-start">
          <CartaoPlano vaiConsumir={vaiConsumir} />
          <ComoFunciona
            um="A IA lê as páginas escolhidas e lista os funcionários e todas as verbas que encontrou."
            dois="Você marca as verbas que precisa e ela extrai os valores de cada uma."
            saida="No fim baixa um Excel com uma aba por funcionário e uma coluna por verba, por mês."
          />
        </div>
      </div>

      <AnimatePresence>
        {ocupado && !mostrarVerbas && (
          <Progresso
            titulo={analisando ? "Identificando verbas" : "Gerando Excel"}
            mensagem={progresso.message}
            atual={progresso.current}
            total={progresso.total}
          />
        )}
      </AnimatePresence>

      {mostrarVerbas && analise && (
        <ModalVerbas
          dados={analise}
          aoFechar={() => { setMostrarVerbas(false); setAnalise(null); }}
          aoConfirmar={verbasConfirmadas}
        />
      )}

      <AnimatePresence>
        {saldoCurto && (
          <ModalSaldo
            pedidas={saldoCurto.pedidas}
            disponiveis={saldoCurto.disponiveis}
            aoFechar={() => setSaldoCurto(null)}
          />
        )}
      </AnimatePresence>
    </CascaNova>
  );
}
