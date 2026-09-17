// frontend/src/novo/PontoNovo.tsx
//
// Extrator de Ponto no layout novo.
//
// A logica e' a mesma da tela atual, chamada por chamada:
//   /api/extract-periods  ->  poll /api/progress/<id>  ->  ModalPeriodos
//   /api/process          ->  poll /api/progress/<id>  ->  /api/download/<id>
// Mudou a forma: duas colunas, o saldo do plano sempre a' vista, e as etapas
// escritas na tela em vez de escondidas no botao.

import { useMemo, useRef, useState } from "react";
import { AnimatePresence } from "framer-motion";
import { Clock, FileText, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useUserPlan } from "@/hooks/useUserPlan";
import WarningsModal, { AvisoItem } from "@/components/WarningsModal";
import CascaNova from "./CascaNova";
import ModalPeriodos, { InfoPagina } from "./ModalPeriodos";
import { AreaUpload, CartaoPlano, ComoFunciona, ModalSaldo, Progresso } from "./Pecas";
import { baixar, buscar, contarPaginas } from "./api";

export default function PontoNovo({ aoVoltarAntigo }: { aoVoltarAntigo?: () => void }) {
  const { plan, canUseExtras, refreshUser } = useUserPlan();

  const [arquivo, setArquivo] = useState<File | null>(null);
  const [intervalo, setIntervalo] = useState("");
  const [quinzenas, setQuinzenas] = useState(false);
  const [noturno, setNoturno] = useState(false);

  const [analisando, setAnalisando] = useState(false);
  const [progAnalise, setProgAnalise] = useState({ current: 0, total: 0, message: "Lendo períodos..." });

  const [paginas, setPaginas] = useState<InfoPagina[] | null>(null);
  const [caminhoPdf, setCaminhoPdf] = useState("");
  const [mostrarPeriodos, setMostrarPeriodos] = useState(false);

  const [processando, setProcessando] = useState(false);
  const [progProcesso, setProgProcesso] = useState({ current: 0, total: 0, message: "Processando..." });

  const [saldoCurto, setSaldoCurto] = useState<{ pedidas: number; disponiveis: number } | null>(null);
  const [avisos, setAvisos] = useState<{
    avisos: AvisoItem[]; totalDias: number; pareados: number; filename: string;
  } | null>(null);

  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const vaiConsumir = useMemo(() => contarPaginas(intervalo), [intervalo]);
  const ocupado = analisando || processando;
  const semSaldo = !canUseExtras && plan.pageBalance <= 0;
  const temSaldo = canUseExtras || plan.pageBalance >= vaiConsumir;
  const progresso = analisando ? progAnalise : progProcesso;

  const acompanhar = (
    taskId: string,
    aoTerminar: (d: Record<string, unknown>) => void,
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
          clearInterval(timer.current!);
          aoTerminar(d);
        } else if (d.status === "error" || d.status === "failed") {
          clearInterval(timer.current!);
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
    setProgAnalise({ current: 0, total: 1, message: "Lendo os períodos do PDF..." });

    const form = new FormData();
    form.append("pdf_file", arquivo);
    form.append("pages", intervalo);
    form.append("quinzenas_nao_sequenciais", String(quinzenas));
    form.append("turno_noturno", String(noturno));

    try {
      const res = await buscar("/api/extract-periods", { method: "POST", body: form });
      if (res.status === 403) {
        const d = await res.json();
        setAnalisando(false);
        setSaldoCurto({ pedidas: vaiConsumir, disponiveis: d.balance ?? plan.pageBalance });
        return;
      }
      const d = await res.json();
      if (d.task_id) {
        acompanhar(d.task_id, (r) => {
          setAnalisando(false);
          const pgs = r.result as InfoPagina[] | undefined;
          const cam = r.pdf_path as string | undefined;
          if (pgs && cam) {
            setPaginas(pgs);
            setCaminhoPdf(cam);
            setMostrarPeriodos(true);
          } else {
            toast.error("Análise não retornou dados de período.");
          }
        }, setProgAnalise);
      } else {
        setAnalisando(false);
        toast.error(d.error || "Falha ao iniciar análise.");
      }
    } catch {
      setAnalisando(false);
      toast.error("Erro de conexão.");
    }
  };

  const periodosConfirmados = (taskId: string) => {
    setMostrarPeriodos(false);
    setProcessando(true);
    setProgProcesso({ current: 0, total: 1, message: "Processando cartões de ponto..." });
    acompanhar(taskId, async (r) => {
      setProcessando(false);
      const nome = (r.filename as string) || "Ponto_Extraido.csv";
      toast.success("Extração concluída! Baixando arquivo...");
      try {
        const res = await buscar(`/api/download/${taskId}`);
        if (res.ok) {
          baixar(await res.blob(), nome);
          const w = r.warnings as AvisoItem[] | undefined;
          if (w?.length) {
            setAvisos({
              avisos: w,
              totalDias: (r.total_dias as number) || 0,
              pareados: (r.pareados as number) || 0,
              filename: nome,
            });
          }
          setTimeout(() => refreshUser(), 1500);
        } else {
          toast.error("Erro ao baixar o arquivo.");
        }
      } catch {
        toast.error("Erro ao baixar o arquivo.");
      }
    }, setProgProcesso);
  };

  const caixa = "glass-card p-[26px]";

  return (
    <CascaNova
      titulo="Extrator de Ponto"
      descricao="Lê cartões de ponto em PDF e devolve um CSV com as marcações em ordem cronológica."
      aoVoltarAntigo={aoVoltarAntigo}
    >
      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-4">
          <div className={caixa}>
            <AreaUpload
              arquivo={arquivo}
              aoEscolher={setArquivo}
              desabilitado={ocupado}
              icone={<Clock className="h-[22px] w-[22px]" />}
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
              placeholder="Ex: 1-10, 15, 20-25"
              disabled={ocupado}
              className="w-full rounded-xl border border-border/50 bg-background/60 px-4 py-3 text-sm text-foreground transition-all placeholder:text-muted-foreground focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/20 disabled:opacity-50"
            />

            <p className="mb-4 mt-5 text-sm font-medium text-foreground">Casos especiais (opcional)</p>
            <label className="flex cursor-pointer items-start gap-3">
              <input
                type="checkbox"
                checked={quinzenas}
                onChange={(e) => setQuinzenas(e.target.checked)}
                disabled={ocupado}
                className="mt-1 h-4 w-4 cursor-pointer rounded border-border accent-primary"
              />
              <span className="flex-1">
                <span className="block text-sm text-foreground">Quinzenas não-sequenciais</span>
                <span className="block text-xs text-muted-foreground">
                  Marque se uma mesma página contém duas tabelas de períodos diferentes
                </span>
              </span>
            </label>
            <label className="mt-3 flex cursor-pointer items-start gap-3">
              <input
                type="checkbox"
                checked={noturno}
                onChange={(e) => setNoturno(e.target.checked)}
                disabled={ocupado}
                className="mt-1 h-4 w-4 cursor-pointer rounded border-border accent-primary"
              />
              <span className="flex-1">
                <span className="block text-sm text-foreground">Plantões noturnos</span>
                <span className="block text-xs text-muted-foreground">
                  Marque se há plantões que começam num dia e terminam no outro
                </span>
              </span>
            </label>
          </div>

          <div className="flex justify-end">
            <button
              onClick={comecar}
              disabled={ocupado || !arquivo || !intervalo.trim()}
              className="flex items-center gap-2 rounded-xl gradient-primary px-8 py-3 text-sm font-bold text-primary-foreground transition-all hover:shadow-lg hover:shadow-primary/25 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {ocupado
                ? <><Loader2 className="h-5 w-5 animate-spin" /> {progresso.message}</>
                : <><FileText className="h-5 w-5" /> Identificar períodos</>}
            </button>
          </div>
        </div>

        <div className="space-y-4 lg:sticky lg:top-[118px] lg:self-start">
          <CartaoPlano vaiConsumir={vaiConsumir} />
          <ComoFunciona
            um="A IA lê as páginas escolhidas e identifica o período de cada cartão."
            dois="Você confere as datas, corrige o que estiver errado e ela extrai as marcações."
            saida="No fim baixa um CSV com o calendário completo do período, uma linha por dia."
          />
        </div>
      </div>

      <AnimatePresence>
        {ocupado && !mostrarPeriodos && (
          <Progresso
            titulo={analisando ? "Identificando períodos" : "Processando ponto"}
            mensagem={progresso.message}
            atual={progresso.current}
            total={progresso.total}
          />
        )}
      </AnimatePresence>

      {mostrarPeriodos && paginas && (
        <ModalPeriodos
          paginas={paginas}
          caminhoPdf={caminhoPdf}
          turnoNoturno={noturno}
          buscar={buscar}
          aoFechar={() => setMostrarPeriodos(false)}
          aoConfirmar={periodosConfirmados}
          aoFaltarSaldo={(pedidas, disponiveis) => {
            setMostrarPeriodos(false);
            setSaldoCurto({ pedidas, disponiveis });
          }}
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

      <AnimatePresence>
        {avisos && (
          <WarningsModal
            avisos={avisos.avisos}
            totalDias={avisos.totalDias}
            pareados={avisos.pareados}
            filename={avisos.filename}
            onClose={() => setAvisos(null)}
          />
        )}
      </AnimatePresence>
    </CascaNova>
  );
}
