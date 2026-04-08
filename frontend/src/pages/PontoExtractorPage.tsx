// frontend/src/pages/PontoExtractorPage.tsx
//
// CORREÇÕES aplicadas vs original:
//   1. Adicionado useUserPlan + canUseExtras
//   2. limitReached = !canUseExtras && pageBalance <= 0   (só free bloqueia)
//   3. hasEnoughPages = canUseExtras || pageBalance >= pagesToConsume
//   4. handleStart verifica limite ANTES de enviar
//   5. PeriodConfirmationModal trata 403 do backend com modal de limite
//   6. handlePeriodConfirm chama refreshUser() após download
//   7. Aviso contextual no título (suave para pago, bloqueante para free)
//
// Todo o resto é IDÊNTICO ao original.

import { useState, useRef, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Link } from "react-router-dom";
import {
  Upload, Play, ArrowLeft, Loader2, X,
  Calendar, FileText, ChevronRight, ToggleLeft, ToggleRight,
  AlertTriangle, CreditCard,
} from "lucide-react";
import { toast } from "sonner";
import AppHeader from "@/components/AppHeader";
import { useUserPlan } from "@/hooks/useUserPlan";  // ← ADICIONADO

// ─────────────────────────────────────────────
// Helpers (idênticos ao original)
// ─────────────────────────────────────────────
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
  return fetch(url, { ...options, headers });
}

function formatDateInput(value: string): string {
  const v = value.replace(/\D/g, "").slice(0, 8);
  if (v.length > 4) return `${v.slice(0, 2)}/${v.slice(2, 4)}/${v.slice(4)}`;
  if (v.length > 2) return `${v.slice(0, 2)}/${v.slice(2)}`;
  return v;
}

function parsePageRange(range: string): number {
  if (!range.trim()) return 0;
  let total = 0;
  for (const part of range.split(",").map((s) => s.trim())) {
    if (part.includes("-")) {
      const [s, e] = part.split("-").map(Number);
      if (!isNaN(s) && !isNaN(e) && e >= s) total += e - s + 1;
    } else if (!isNaN(Number(part)) && part) total += 1;
  }
  return total;
}

const DATE_RE = /^\d{2}\/\d{2}\/\d{4}$/;

// ─────────────────────────────────────────────
// Types (idênticos ao original)
// ─────────────────────────────────────────────
interface Period {
  start_date: string;
  end_date: string;
}

interface PageInfo {
  page_number: number;
  page_index: number;
  period: Period | null;
  is_active: boolean;
}

// ─────────────────────────────────────────────
// Modal de Confirmação de Períodos
// ─────────────────────────────────────────────
// ALTERAÇÃO: adicionado onInsufficientBalance para tratar 403 do /api/process
function PeriodConfirmationModal({
  pages,
  pdfPath,
  onClose,
  onConfirm,
  onInsufficientBalance,
}: {
  pages: PageInfo[];
  pdfPath: string;
  onClose: () => void;
  onConfirm: (taskId: string) => void;
  onInsufficientBalance: (requested: number, available: number) => void; // ← ADICIONADO
}) {
  const [items, setItems] = useState<PageInfo[]>(
    pages.map((p) => ({
      ...p,
      is_active: true,
      period: p.period ?? { start_date: "", end_date: "" },
    }))
  );
  const [loading, setLoading] = useState(false);

  const activeCount = items.filter((p) => p.is_active).length;

  const handleDateChange = (index: number, field: keyof Period, raw: string) => {
    const val = formatDateInput(raw);
    setItems((prev) => {
      const next = [...prev];
      next[index] = {
        ...next[index],
        period: { ...(next[index].period ?? { start_date: "", end_date: "" }), [field]: val },
      };
      return next;
    });
  };

  const handleToggle = (index: number) => {
    setItems((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], is_active: !next[index].is_active };
      return next;
    });
  };

  const handleApplyPattern = (startIndex: number) => {
    const seed = items[startIndex]?.period;
    if (!seed || !DATE_RE.test(seed.start_date) || !DATE_RE.test(seed.end_date)) {
      toast.warning("Preencha o período completo (DD/MM/AAAA) antes de aplicar.");
      return;
    }
    const parse = (s: string) => {
      const [d, m, y] = s.split("/");
      return new Date(+y, +m - 1, +d);
    };
    const fmt = (dt: Date) =>
      `${String(dt.getDate()).padStart(2, "0")}/${String(dt.getMonth() + 1).padStart(2, "0")}/${dt.getFullYear()}`;
    const isLastDay = (dt: Date) => {
      const next = new Date(dt);
      next.setDate(next.getDate() + 1);
      return next.getDate() === 1;
    };
    let lastStart = parse(seed.start_date);
    let lastEnd = parse(seed.end_date);
    const endWasLast = isLastDay(lastEnd);
    setItems((prev) => {
      const next = [...prev];
      for (let i = startIndex + 1; i < next.length; i++) {
        if (!next[i].is_active) continue;
        const ns = new Date(lastStart);
        ns.setMonth(ns.getMonth() + 1);
        const ne = endWasLast
          ? new Date(ns.getFullYear(), ns.getMonth() + 1, 0)
          : (() => { const d = new Date(lastEnd); d.setMonth(d.getMonth() + 1); return d; })();
        next[i] = { ...next[i], period: { start_date: fmt(ns), end_date: fmt(ne) } };
        lastStart = ns;
        lastEnd = ne;
      }
      return next;
    });
  };

  const handleConfirm = async () => {
    const valid = items.filter(
      (p) => p.is_active && p.period && DATE_RE.test(p.period.start_date) && DATE_RE.test(p.period.end_date)
    );
    if (valid.length === 0) {
      toast.warning("Preencha o período (DD/MM/AAAA) de pelo menos uma página ativa.");
      return;
    }
    setLoading(true);
    try {
      const res = await apiFetch("/api/process", {
        method: "POST",
        body: JSON.stringify({ pdf_path: pdfPath, pages_with_periods: valid, model_type: "6" }),
      });
      const data = await res.json();

      // ← ADICIONADO: trata 403 de saldo insuficiente (só free trial)
      if (res.status === 403) {
        onInsufficientBalance(data.pages_requested ?? valid.length, data.balance ?? 0);
        return;
      }

      if (res.ok && data.task_id) {
        toast.success("Processamento iniciado!");
        onConfirm(data.task_id);
      } else {
        toast.error(data.error || "Erro ao iniciar processamento.");
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
          className="glass-card w-full max-w-2xl max-h-[85vh] flex flex-col relative"
        >
          {/* Header do modal */}
          <div className="flex items-center justify-between p-6 border-b border-border/50 shrink-0">
            <div className="flex items-center gap-3">
              <Calendar className="w-5 h-5 text-primary" />
              <h3 className="text-lg font-bold text-foreground">Confirmar Períodos</h3>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground">{activeCount} página(s) ativa(s)</span>
              <button
                onClick={onClose}
                className="text-muted-foreground hover:text-foreground transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Lista de páginas */}
          <div className="overflow-y-auto flex-1 p-4 space-y-2">
            {items.map((page, index) => (
              <motion.div
                key={page.page_index}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.03 }}
                className={`flex items-center gap-3 p-3 rounded-xl border transition-all ${
                  page.is_active
                    ? "border-border/50 bg-secondary/20"
                    : "border-border/20 bg-secondary/5 opacity-45"
                }`}
              >
                <button
                  onClick={() => handleToggle(index)}
                  className="flex items-center justify-center text-muted-foreground hover:text-primary transition-colors"
                  title={page.is_active ? "Desativar" : "Ativar"}
                >
                  {page.is_active
                    ? <ToggleRight className="w-5 h-5 text-primary" />
                    : <ToggleLeft className="w-5 h-5" />}
                </button>

                <span className="text-sm font-semibold text-foreground">
                  Pág {page.page_number}
                </span>

                <input
                  type="text"
                  value={page.period?.start_date ?? ""}
                  onChange={(e) => handleDateChange(index, "start_date", e.target.value)}
                  placeholder="DD/MM/AAAA"
                  maxLength={10}
                  disabled={!page.is_active}
                  className={`w-full px-3 py-2 rounded-lg bg-background/60 border text-foreground text-sm focus:outline-none transition-all disabled:opacity-40 ${
                    page.period?.start_date && DATE_RE.test(page.period.start_date)
                      ? "border-success/50 focus:border-success/80 focus:ring-1 focus:ring-success/20"
                      : "border-border/50 focus:border-primary/60 focus:ring-1 focus:ring-primary/20"
                  }`}
                />

                <ChevronRight className="w-4 h-4 text-muted-foreground" />

                <input
                  type="text"
                  value={page.period?.end_date ?? ""}
                  onChange={(e) => handleDateChange(index, "end_date", e.target.value)}
                  placeholder="DD/MM/AAAA"
                  maxLength={10}
                  disabled={!page.is_active}
                  className={`w-full px-3 py-2 rounded-lg bg-background/60 border text-foreground text-sm focus:outline-none transition-all disabled:opacity-40 ${
                    page.period?.end_date && DATE_RE.test(page.period.end_date)
                      ? "border-success/50 focus:border-success/80 focus:ring-1 focus:ring-success/20"
                      : "border-border/50 focus:border-primary/60 focus:ring-1 focus:ring-primary/20"
                  }`}
                />

                <button
                  onClick={() => handleApplyPattern(index)}
                  disabled={!page.is_active}
                  title="Preencher próximas páginas com padrão mensal"
                  className="text-xs px-2 py-1.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-all disabled:opacity-30 font-medium whitespace-nowrap"
                >
                  Aplicar ↓
                </button>
              </motion.div>
            ))}
          </div>

          {/* Footer do modal */}
          <div className="flex gap-3 p-6 border-t border-border/50 shrink-0">
            <button
              onClick={onClose}
              disabled={loading}
              className="flex-1 py-3 rounded-lg border border-border text-foreground text-sm font-medium hover:bg-surface-hover transition-all disabled:opacity-50"
            >
              Cancelar
            </button>
            <button
              onClick={handleConfirm}
              disabled={loading || activeCount === 0}
              className="flex-1 py-3 rounded-xl gradient-primary text-primary-foreground text-sm font-bold flex items-center justify-center gap-2 hover:shadow-lg hover:shadow-primary/25 transition-all disabled:opacity-50"
            >
              {loading
                ? <><Loader2 className="w-4 h-4 animate-spin" /> Iniciando...</>
                : <><Play className="w-4 h-4" /> Confirmar e Extrair</>}
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
const PontoExtractorPage = () => {
  // ← ADICIONADO: lê canUseExtras para saber se é plano pago
  const { plan, canUseExtras, refreshUser } = useUserPlan();

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [pageRange, setPageRange] = useState("");

  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState({ current: 0, total: 0, message: "Lendo períodos..." });

  const [pagesData, setPagesData] = useState<PageInfo[] | null>(null);
  const [pdfPath, setPdfPath] = useState("");
  const [showPeriodModal, setShowPeriodModal] = useState(false);

  const [isProcessing, setIsProcessing] = useState(false);
  const [processProgress, setProcessProgress] = useState({ current: 0, total: 0, message: "Processando..." });

  // ← ADICIONADO: modal de saldo insuficiente (só para free trial)
  const [showLimitAlert, setShowLimitAlert]   = useState(false);
  const [limitAlertData, setLimitAlertData]   = useState({ requested: 0, available: 0 });

  const pollingRef  = useRef<ReturnType<typeof setInterval> | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ← ADICIONADO: cálculo de saldo baseado no range digitado
  const pagesToConsume = useMemo(() => parsePageRange(pageRange), [pageRange]);

  // ── REGRA CENTRAL ──────────────────────────────────────────────────────────
  // Plano pago: NUNCA bloqueia — extras são cobráveis
  // Free trial: bloqueia quando saldo = 0
  const limitReached   = !canUseExtras && plan.pageBalance <= 0;
  const hasEnoughPages = canUseExtras   || plan.pageBalance >= pagesToConsume;
  // ──────────────────────────────────────────────────────────────────────────

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
    onDone: (data: Record<string, unknown>) => void,
    setProgress: (p: { current: number; total: number; message: string }) => void
  ) => {
    if (pollingRef.current) clearInterval(pollingRef.current);
    pollingRef.current = setInterval(async () => {
      try {
        const res = await apiFetch(`/api/progress/${taskId}`);
        const data = await res.json();
        if (data.current_step !== undefined) {
          setProgress({ current: data.current_step, total: data.total_steps || 1, message: data.message || "Processando..." });
        }
        if (data.status === "completed") {
          clearInterval(pollingRef.current!);
          onDone(data);
        } else if (data.status === "error" || data.status === "failed") {
          clearInterval(pollingRef.current!);
          toast.error(data.error || "Erro no processamento.");
          setIsAnalyzing(false);
          setIsProcessing(false);
        }
      } catch { /* rede instável */ }
    }, 2000);
  };

  const handleStart = async () => {
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
    setAnalysisProgress({ current: 0, total: 1, message: "Lendo os períodos do PDF..." });

    const formData = new FormData();
    formData.append("pdf_file", selectedFile);
    formData.append("pages", pageRange);

    try {
      const res = await apiFetch("/api/extract-periods", { method: "POST", body: formData });

      // ← ADICIONADO: trata 403 (free esgotado detectado pelo backend)
      if (res.status === 403) {
        const data = await res.json();
        setIsAnalyzing(false);
        setLimitAlertData({ requested: pagesToConsume, available: data.balance ?? plan.pageBalance });
        setShowLimitAlert(true);
        return;
      }

      const data = await res.json();
      if (data.task_id) {
        pollProgress(
          data.task_id,
          (result) => {
            setIsAnalyzing(false);
            const pages = result.result as PageInfo[] | undefined;
            const path = result.pdf_path as string | undefined;
            if (pages && path) {
              setPagesData(pages);
              setPdfPath(path);
              setShowPeriodModal(true);
            } else {
              toast.error("Análise não retornou dados de período.");
            }
          },
          setAnalysisProgress
        );
      } else {
        setIsAnalyzing(false);
        toast.error(data.error || "Falha ao iniciar análise.");
      }
    } catch {
      setIsAnalyzing(false);
      toast.error("Erro de conexão.");
    }
  };

  const handlePeriodConfirm = (taskId: string) => {
    setShowPeriodModal(false);
    setIsProcessing(true);
    setProcessProgress({ current: 0, total: 1, message: "Processando cartões de ponto..." });
    pollProgress(
      taskId,
      async (result) => {
        setIsProcessing(false);
        toast.success("Extração concluída!");
        setTimeout(() => refreshUser(), 1500); // ← ADICIONADO: atualiza saldo após processamento
        const downloadRes = await apiFetch(`/api/download/${taskId}`);
        const blob = await downloadRes.blob();
        triggerDownload(blob, (result.filename as string) || `Ponto_${taskId}.csv`);
      },
      setProcessProgress
    );
  };

  // ← ADICIONADO: callback para quando /api/process retorna 403
  const handleInsufficientBalance = (requested: number, available: number) => {
    setShowPeriodModal(false);
    setLimitAlertData({ requested, available });
    setShowLimitAlert(true);
  };

  const isBusy = isAnalyzing || isProcessing;
  const currentProgress = isProcessing ? processProgress : analysisProgress;
  const progressPct = currentProgress.total > 0
    ? Math.round((currentProgress.current / currentProgress.total) * 100)
    : 0;

  return (
    <div className="min-h-screen gradient-bg flex flex-col">
      <AppHeader />

      <main className="flex-1 flex items-center justify-center p-6">
        {/* Layout idêntico ao original (max-w-4xl glass-card) */}
        <div className="glass-card p-8 w-full max-w-4xl">
          <div className="flex items-center gap-3 mb-6">
            <Link
              to="/app"
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <h3 className="text-lg font-semibold text-foreground">Extrator de Ponto</h3>
          </div>

          {/* ← ADICIONADO: avisos contextuais abaixo do título */}
          {canUseExtras && plan.pageBalance <= 0 && (
            <p className="text-xs text-amber-500 mb-4">
              Limite incluído atingido — próximas páginas serão cobradas à parte.
            </p>
          )}
          {!canUseExtras && plan.pageBalance > 0 && plan.pageBalance <= 5 && (
            <p className="text-xs text-amber-500 mb-4">
              ⚠ Apenas {plan.pageBalance} página(s) restante(s) no plano gratuito.
            </p>
          )}
          {limitReached && (
            <p className="text-xs text-destructive mb-4">
              Saldo esgotado.{" "}
              <a href="/#pricing" className="underline font-medium">Assine um plano</a>{" "}
              para continuar.
            </p>
          )}

          {/* Inputs — idênticos ao original */}
          <div className="flex flex-col sm:flex-row gap-4">
            <input
              type="file"
              accept=".pdf"
              ref={fileInputRef}
              style={{ display: "none" }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) { setSelectedFile(file); toast.success(`PDF "${file.name}" importado.`); }
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

          {/* Botão principal — idêntico ao original, sem estado "Assinar Plano" para pagos */}
          <button
            onClick={handleStart}
            disabled={isBusy || !selectedFile || !pageRange.trim() || limitReached}
            className="w-full mt-6 gradient-primary text-primary-foreground py-4 rounded-xl font-bold text-base flex items-center justify-center gap-2 hover:shadow-lg hover:shadow-primary/25 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {isBusy ? (
              <><Loader2 className="w-5 h-5 animate-spin" /> {currentProgress.message}</>
            ) : (
              <><FileText className="w-5 h-5" /> Identificar Períodos</>
            )}
          </button>
        </div>
      </main>

      {/* Modal de progresso — idêntico ao original */}
      <AnimatePresence>
        {isBusy && !showPeriodModal && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 backdrop-blur-sm p-4"
          >
            <motion.div
              initial={{ scale: 0.95, y: 10 }} animate={{ scale: 1, y: 0 }}
              className="glass-card p-8 max-w-sm w-full text-center"
            >
              <Loader2 className="w-12 h-12 animate-spin text-primary mx-auto mb-4" />
              <h3 className="text-lg font-bold text-foreground mb-2">
                {isAnalyzing ? "Identificando Períodos" : "Extraindo Ponto"}
              </h3>
              <p className="text-muted-foreground text-sm mb-5">{currentProgress.message}</p>
              {currentProgress.total > 0 && (
                <div className="space-y-2">
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Página {currentProgress.current} de {currentProgress.total}</span>
                    <span>{progressPct}%</span>
                  </div>
                  <div className="w-full bg-secondary rounded-full h-2 overflow-hidden">
                    <motion.div
                      className="h-full gradient-primary rounded-full"
                      animate={{ width: `${progressPct}%` }}
                      transition={{ duration: 0.4 }}
                    />
                  </div>
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Modal de confirmação de períodos */}
      {showPeriodModal && pagesData && (
        <PeriodConfirmationModal
          pages={pagesData}
          pdfPath={pdfPath}
          onClose={() => { setShowPeriodModal(false); setIsAnalyzing(false); }}
          onConfirm={handlePeriodConfirm}
          onInsufficientBalance={handleInsufficientBalance} // ← ADICIONADO
        />
      )}

      {/* ← ADICIONADO: Modal de saldo insuficiente (só aparece para free trial) */}
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
                <p className="text-muted-foreground text-sm mb-2">
                  {limitAlertData.requested > 0
                    ? `Você precisa de ${limitAlertData.requested} página(s), mas tem apenas ${limitAlertData.available} disponível(is).`
                    : "Suas páginas grátis foram totalmente utilizadas."}
                </p>
                <p className="text-muted-foreground text-xs mb-6">
                  Assine um plano para continuar processando seus cartões de ponto.
                </p>
                <div className="flex gap-3">
                  <button
                    onClick={() => setShowLimitAlert(false)}
                    className="flex-1 py-3 rounded-lg border border-border text-foreground text-sm font-medium hover:bg-surface-hover transition-all"
                  >
                    Fechar
                  </button>
                  <a href="/#pricing" className="flex-1">
                    <button className="w-full py-3 rounded-lg gradient-primary text-primary-foreground text-sm font-bold hover:shadow-lg hover:shadow-primary/25 transition-all flex items-center justify-center gap-2">
                      <CreditCard className="w-4 h-4" /> Ver Planos
                    </button>
                  </a>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default PontoExtractorPage;
