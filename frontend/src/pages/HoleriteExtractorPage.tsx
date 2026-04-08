// frontend/src/pages/HoleriteExtractorPage.tsx
//
// CORREÇÕES aplicadas vs original:
//   1. Adicionado useUserPlan + canUseExtras
//   2. limitReached = !canUseExtras && pageBalance <= 0   (só free bloqueia)
//   3. hasEnoughPages = canUseExtras || pageBalance >= pagesToConsume
//   4. Adicionado parsePageRange + pagesToConsume (useMemo)
//   5. handleStartAnalysis verifica limite ANTES de enviar
//   6. Feedback de páginas em tempo real (igual ao PontoExtractorPage)
//   7. Aviso de saldo baixo (≤5 páginas) para free trial
//   8. refreshUser() chamado após download
//   9. Botão de upload já tinha disabled={isAnalyzing || isProcessing} — mantido
//
// Todo o resto é IDÊNTICO ao original.

import { useState, useRef, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Link } from "react-router-dom";
import {
  Upload, Play, ArrowLeft, Loader2, X, Check, FileText,
  AlertTriangle, CreditCard,
} from "lucide-react";
import { toast } from "sonner";
import AppHeader from "@/components/AppHeader";
import { useUserPlan } from "@/hooks/useUserPlan";

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────

// ← ADICIONADO: calcula quantas páginas o range representa
function parsePageRange(range: string): number {
  if (!range.trim()) return 0;
  let total = 0;
  const parts = range.split(",").map((s) => s.trim());
  for (const part of parts) {
    if (part.includes("-")) {
      const [start, end] = part.split("-").map(Number);
      if (!isNaN(start) && !isNaN(end) && end >= start) total += end - start + 1;
    } else {
      if (!isNaN(Number(part)) && part) total += 1;
    }
  }
  return total;
}

const API_BASE_URL = "";

function getToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("jwt_token");
}

async function apiFetch(url: string, options: RequestInit = {}) {
  const token = getToken();
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    ...(options.headers as Record<string, string>),
  };
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`${API_BASE_URL}${url}`, { ...options, headers });
  return res;
}

// ─────────────────────────────────────────────
// Modal de Seleção de Verbas (idêntico ao original)
// ─────────────────────────────────────────────
interface AnalysisData {
  nomes: string[];
  verbas: string[];
  pdf_path: string;
  pages: string;
}

function VerbaSelectionModal({
  data,
  onClose,
  onConfirm,
}: {
  data: AnalysisData;
  onClose: () => void;
  onConfirm: (taskId: string) => void;
}) {
  const [selectedVerbas, setSelectedVerbas] = useState<string[]>(data.verbas || []);
  const [loading, setLoading] = useState(false);

  const toggleVerba = (verba: string) => {
    setSelectedVerbas((prev) =>
      prev.includes(verba) ? prev.filter((v) => v !== verba) : [...prev, verba]
    );
  };

  const selectAll = () => setSelectedVerbas([...data.verbas]);
  const deselectAll = () => setSelectedVerbas([]);

  const handleConfirm = async () => {
    if (selectedVerbas.length === 0) {
      toast.warning("Selecione pelo menos uma verba.");
      return;
    }
    setLoading(true);
    try {
      const res = await apiFetch("/api/payroll/process", {
        method: "POST",
        body: JSON.stringify({
          pdf_path: data.pdf_path,
          pages: data.pages,
          selected_verbas: selectedVerbas,
        }),
      });
      const resData = await res.json();
      if (res.ok && resData.task_id) {
        toast.success("Processamento iniciado!");
        onConfirm(resData.task_id);
      } else {
        toast.error(resData.error || "Erro ao iniciar processamento.");
      }
    } catch {
      toast.error("Erro de conexão.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 backdrop-blur-sm p-4"
      >
        <motion.div
          initial={{ scale: 0.95, y: 10 }}
          animate={{ scale: 1, y: 0 }}
          exit={{ scale: 0.95, y: 10 }}
          className="glass-card w-full max-w-2xl relative flex flex-col max-h-[90vh]"
        >
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-border/50 shrink-0">
            <div>
              <h3 className="text-lg font-bold text-foreground">Configurar Extração</h3>
              {data.nomes.length > 0 && (
                <p className="text-sm text-muted-foreground mt-1">
                  Funcionários: {data.nomes.join(", ")}
                </p>
              )}
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary/60 transition-all"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Verbas */}
          <div className="p-6 flex-1 overflow-hidden flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h4 className="text-sm font-semibold text-foreground">
                Selecione as verbas/itens ({selectedVerbas.length}/{data.verbas.length})
              </h4>
              <div className="flex gap-2">
                <button
                  onClick={selectAll}
                  className="text-xs px-3 py-1.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-all"
                >
                  Todos
                </button>
                <button
                  onClick={deselectAll}
                  className="text-xs px-3 py-1.5 rounded-lg bg-secondary/60 text-muted-foreground hover:bg-secondary transition-all"
                >
                  Nenhum
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 overflow-y-auto pr-1">
              {data.verbas.map((verba, i) => {
                const selected = selectedVerbas.includes(verba);
                return (
                  <button
                    key={i}
                    onClick={() => toggleVerba(verba)}
                    className={`flex items-center gap-3 p-3 rounded-lg border text-left transition-all text-sm ${
                      selected
                        ? "border-primary/50 bg-primary/10 text-foreground"
                        : "border-border/40 bg-secondary/30 text-muted-foreground hover:border-border hover:text-foreground"
                    }`}
                  >
                    <div
                      className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-all ${
                        selected ? "bg-primary border-primary" : "border-border/60"
                      }`}
                    >
                      {selected && <Check className="w-3 h-3 text-primary-foreground" />}
                    </div>
                    <span className="truncate">{verba}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Footer */}
          <div className="flex gap-3 p-6 border-t border-border/50 shrink-0">
            <button
              onClick={onClose}
              className="flex-1 py-3 rounded-lg border border-border text-foreground text-sm font-medium hover:bg-surface-hover transition-all"
            >
              Cancelar
            </button>
            <button
              onClick={handleConfirm}
              disabled={loading || selectedVerbas.length === 0}
              className="flex-1 py-3 rounded-xl gradient-primary text-primary-foreground text-sm font-bold flex items-center justify-center gap-2 hover:shadow-lg hover:shadow-primary/25 transition-all disabled:opacity-50"
            >
              {loading ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Iniciando...</>
              ) : (
                <><Play className="w-4 h-4" /> Confirmar e Gerar Excel</>
              )}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

// ─────────────────────────────────────────────
// Página Principal
// ─────────────────────────────────────────────
const HoleriteExtractorPage = () => {
  // ← ADICIONADO: lê canUseExtras para saber se é plano pago
  const { plan, canUseExtras, refreshUser } = useUserPlan();

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [pageRange, setPageRange] = useState("");

  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState({ current: 0, total: 0, message: "Analisando..." });

  const [analysisData, setAnalysisData] = useState<AnalysisData | null>(null);
  const [showModal, setShowModal] = useState(false);

  const [isProcessing, setIsProcessing] = useState(false);
  const [processProgress, setProcessProgress] = useState({ current: 0, total: 0, message: "Processando..." });

  // ← ADICIONADO: modal de saldo insuficiente
  const [showLimitAlert, setShowLimitAlert] = useState(false);
  const [limitAlertData, setLimitAlertData] = useState({ requested: 0, available: 0 });

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ← ADICIONADO: cálculo de saldo baseado no range digitado
  const pagesToConsume = useMemo(() => parsePageRange(pageRange), [pageRange]);

  // ── REGRA CENTRAL ──────────────────────────────────────────────────────────
  // Plano pago: NUNCA bloqueia — extras são cobráveis
  // Free trial: bloqueia quando saldo = 0
  const limitReached   = !canUseExtras && plan.pageBalance <= 0;
  const hasEnoughPages = canUseExtras   || plan.pageBalance >= pagesToConsume;
  // ───────────────────────────────────────────────────────────────────────────

  const isBusy = isAnalyzing || isProcessing;

  const triggerDownload = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const pollProgress = (
    taskId: string,
    onDone: (data: { filename?: string; result?: AnalysisData }) => void,
    setProgress: (p: { current: number; total: number; message: string }) => void
  ) => {
    if (pollingRef.current) clearInterval(pollingRef.current);
    pollingRef.current = setInterval(async () => {
      try {
        const res = await apiFetch(`/api/progress/${taskId}`);
        const data = await res.json();

        if (data.current_step !== undefined) {
          setProgress({
            current: data.current_step,
            total: data.total_steps || 1,
            message: data.message || "Processando...",
          });
        }

        if (data.status === "completed") {
          if (pollingRef.current) clearInterval(pollingRef.current);
          onDone(data);
        } else if (data.status === "error" || data.status === "failed") {
          if (pollingRef.current) clearInterval(pollingRef.current);
          toast.error(data.error || "Erro no processamento.");
          setIsAnalyzing(false);
          setIsProcessing(false);
        }
      } catch {
        // erro de rede, continua tentando
      }
    }, 2000);
  };

  const handleStartAnalysis = async () => {
    if (!selectedFile || !pageRange.trim()) {
      toast.warning("Selecione um PDF e informe as páginas.");
      return;
    }

    // ← ADICIONADO: só bloqueia free trial esgotado ou sem saldo suficiente
    if (limitReached || !hasEnoughPages) {
      setLimitAlertData({ requested: pagesToConsume, available: plan.pageBalance });
      setShowLimitAlert(true);
      return;
    }

    setIsAnalyzing(true);
    setAnalysisProgress({ current: 0, total: 1, message: "Enviando PDF para análise..." });

    const formData = new FormData();
    formData.append("pdf_file", selectedFile);
    formData.append("pages", pageRange);

    try {
      const res = await apiFetch("/api/payroll/analyze", { method: "POST", body: formData });
      const data = await res.json();

      if (data.task_id) {
        pollProgress(
          data.task_id,
          (result: { result?: AnalysisData; filename?: string }) => {
            setIsAnalyzing(false);
            if (result.result) {
              setAnalysisData({ ...result.result, pages: pageRange });
              setShowModal(true);
            } else {
              toast.error("Análise não retornou dados.");
            }
          },
          setAnalysisProgress
        );
      } else {
        setIsAnalyzing(false);
        toast.error("Falha ao iniciar análise.");
      }
    } catch {
      setIsAnalyzing(false);
      toast.error("Erro de conexão.");
    }
  };

  const handleProcessConfirm = (taskId: string) => {
    setShowModal(false);
    setIsProcessing(true);
    setProcessProgress({ current: 0, total: 1, message: "Processando holerite..." });

    pollProgress(
      taskId,
      async (data: { filename?: string }) => {
        setIsProcessing(false);
        toast.success("Holerite gerado com sucesso!");

        const downloadRes = await apiFetch(`/api/download/${taskId}`);
        const blob = await downloadRes.blob();
        const filename = data.filename || `Folha_${taskId}.xlsx`;
        triggerDownload(blob, filename);

        // ← ADICIONADO: atualiza saldo do usuário após download
        await refreshUser();
      },
      setProcessProgress
    );
  };

  return (
    <div className="min-h-screen gradient-bg flex flex-col">
      <AppHeader />

      <main className="flex-1 flex items-center justify-center p-6">
        <div className="glass-card p-8 w-full max-w-4xl">

          {/* Cabeçalho */}
          <div className="flex items-center gap-3 mb-6">
            <Link to="/app" className="text-muted-foreground hover:text-foreground transition-colors">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <h3 className="text-lg font-semibold text-foreground">Extrator de Holerite</h3>
          </div>

          {/* ← ADICIONADO: banner de saldo esgotado para free trial */}
          {limitReached && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center justify-between gap-4 p-4 rounded-lg bg-warning/10 border border-warning/30 mb-6"
            >
              <div className="flex items-center gap-3">
                <AlertTriangle className="w-5 h-5 text-warning shrink-0" />
                <p className="text-sm text-foreground">
                  <span className="font-semibold">Seu limite de teste acabou.</span>{" "}
                  Adquira um plano para continuar processando.
                </p>
              </div>
              <Link
                to="/#pricing"
                className="gradient-primary text-primary-foreground px-5 py-2 rounded-lg text-sm font-semibold whitespace-nowrap hover:shadow-lg hover:shadow-primary/25 transition-all flex items-center gap-2"
              >
                <CreditCard className="w-4 h-4" />
                Ver Planos
              </Link>
            </motion.div>
          )}

          {/* ← ADICIONADO: aviso de saldo baixo (≤5 páginas) para free trial */}
          {!canUseExtras && plan.pageBalance > 0 && plan.pageBalance <= 5 && (
            <p className="text-xs text-amber-500 mb-4">
              ⚠ Apenas {plan.pageBalance} página(s) restante(s) no plano gratuito.
            </p>
          )}

          {/* Inputs */}
          <div className="flex flex-col sm:flex-row gap-4">
            <input
              type="file"
              accept=".pdf"
              ref={fileInputRef}
              style={{ display: "none" }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  setSelectedFile(file);
                  toast.success(`PDF "${file.name}" importado.`);
                }
              }}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isBusy}
              className="flex-1 flex items-center justify-center gap-2 py-3 rounded-lg border border-border bg-secondary/50 text-foreground text-sm font-medium hover:bg-surface-hover transition-all disabled:opacity-50"
            >
              <Upload className="w-4 h-4 text-primary" />
              {selectedFile
                ? selectedFile.name.substring(0, 30) + (selectedFile.name.length > 30 ? "…" : "")
                : "Importar PDF"}
            </button>
            <input
              type="text"
              value={pageRange}
              onChange={(e) => setPageRange(e.target.value)}
              placeholder="Páginas (ex: 1-5, 8, 10-12)"
              disabled={isBusy}
              className="flex-1 px-4 py-3 bg-background/60 border border-border rounded-lg text-foreground placeholder:text-muted-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all disabled:opacity-50"
            />
          </div>

          {/* ← ADICIONADO: feedback de saldo em tempo real ao digitar o range */}
          {pagesToConsume > 0 && !limitReached && (
            <p className={`text-xs mt-2 ${
              canUseExtras
                ? plan.pageBalance <= 0
                  ? "text-amber-500"
                  : plan.pageBalance >= pagesToConsume
                    ? "text-muted-foreground"
                    : "text-amber-500"
                : hasEnoughPages ? "text-muted-foreground" : "text-destructive"
            }`}>
              {canUseExtras
                ? plan.pageBalance <= 0
                  ? `${pagesToConsume} pág. — serão cobradas como extras`
                  : plan.pageBalance >= pagesToConsume
                    ? `${pagesToConsume} pág. incluídas · restam ${plan.pageBalance - pagesToConsume} após`
                    : `${plan.pageBalance} incluídas + ${pagesToConsume - plan.pageBalance} extras`
                : hasEnoughPages
                  ? `${pagesToConsume} pág. · restam ${plan.pageBalance - pagesToConsume} após`
                  : `Saldo insuficiente: precisa de ${pagesToConsume}, tem ${plan.pageBalance}`
              }
            </p>
          )}

          {/* Botão principal */}
          <button
            onClick={handleStartAnalysis}
            disabled={isBusy || !selectedFile || !pageRange.trim() || limitReached}
            className="w-full mt-6 gradient-primary text-primary-foreground py-4 rounded-xl font-bold text-base flex items-center justify-center gap-2 hover:shadow-lg hover:shadow-primary/25 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {isAnalyzing ? (
              <><Loader2 className="w-5 h-5 animate-spin" /> {analysisProgress.message}</>
            ) : isProcessing ? (
              <><Loader2 className="w-5 h-5 animate-spin" /> {processProgress.message}</>
            ) : (
              <><FileText className="w-5 h-5" /> Identificar Itens</>
            )}
          </button>
        </div>
      </main>

      {/* Modal de progresso */}
      <AnimatePresence>
        {isBusy && !showModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 backdrop-blur-sm p-4"
          >
            <motion.div
              initial={{ scale: 0.95, y: 10 }}
              animate={{ scale: 1, y: 0 }}
              className="glass-card p-8 max-w-sm w-full text-center"
            >
              <Loader2 className="w-12 h-12 animate-spin text-primary mx-auto mb-4" />
              <h3 className="text-lg font-bold text-foreground mb-2">
                {isAnalyzing ? "Identificando Verbas" : "Gerando Excel"}
              </h3>
              <p className="text-muted-foreground text-sm mb-4">
                {isAnalyzing ? analysisProgress.message : processProgress.message}
              </p>
              {(() => {
                const p = isAnalyzing ? analysisProgress : processProgress;
                return p.total > 0 ? (
                  <>
                    <div className="w-full bg-secondary/60 rounded-full h-2 mb-2">
                      <div
                        className="h-2 rounded-full gradient-primary transition-all duration-500"
                        style={{ width: `${Math.round((p.current / p.total) * 100)}%` }}
                      />
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Página {p.current} de {p.total}
                    </p>
                  </>
                ) : null;
              })()}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Modal de Seleção de Verbas */}
      {showModal && analysisData && (
        <VerbaSelectionModal
          data={analysisData}
          onClose={() => {
            setShowModal(false);
            setAnalysisData(null);
          }}
          onConfirm={handleProcessConfirm}
        />
      )}

      {/* ← ADICIONADO: modal de saldo insuficiente (igual ao PontoExtractorPage) */}
      <AnimatePresence>
        {showLimitAlert && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 backdrop-blur-sm p-4"
          >
            <motion.div
              initial={{ scale: 0.95, y: 10 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.95, y: 10 }}
              className="glass-card p-8 max-w-md w-full relative"
            >
              <button
                onClick={() => setShowLimitAlert(false)}
                className="absolute top-4 right-4 text-muted-foreground hover:text-foreground"
              >
                <X className="w-5 h-5" />
              </button>
              <div className="text-center">
                <div className="w-16 h-16 rounded-full bg-warning/15 flex items-center justify-center mx-auto mb-4">
                  <AlertTriangle className="w-8 h-8 text-warning" />
                </div>
                <h3 className="text-xl font-bold text-foreground mb-2">Saldo Insuficiente</h3>
                <p className="text-muted-foreground text-sm mb-6">
                  Você precisa de {limitAlertData.requested} página(s), mas só tem{" "}
                  {limitAlertData.available} disponível(is).
                </p>
                <div className="flex gap-3">
                  <button
                    onClick={() => setShowLimitAlert(false)}
                    className="flex-1 py-3 rounded-lg border border-border text-foreground text-sm font-medium hover:bg-surface-hover transition-all"
                  >
                    Fechar
                  </button>
                  <Link to="/#pricing" className="flex-1">
                    <button className="w-full py-3 rounded-lg gradient-primary text-primary-foreground text-sm font-bold hover:shadow-lg hover:shadow-primary/25 transition-all flex items-center justify-center gap-2">
                      <CreditCard className="w-4 h-4" />
                      Ver Planos
                    </button>
                  </Link>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default HoleriteExtractorPage;
