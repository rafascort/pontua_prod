// frontend/src/components/WarningsModal.tsx
//
// Modal de avisos exibido APÓS o download automático do CSV.
// Aparece sempre que um job é concluído, mesmo sem avisos (mostra mensagem de sucesso).
// Só fecha quando o usuário clica em "OK, entendi" ou no X.

import { motion } from "framer-motion";
import { X, AlertTriangle, CheckCircle2 } from "lucide-react";

export interface AvisoItem {
  data: string;
  severidade: "info" | "warning" | "danger";
  mensagem: string;
}

interface WarningsModalProps {
  avisos: AvisoItem[];
  totalDias: number;
  pareados: number;
  filename?: string;
  onClose: () => void;
}

export default function WarningsModal({
  avisos,
  totalDias,
  pareados,
  filename,
  onClose,
}: WarningsModalProps) {
  // Filtra apenas warnings e danger (info não vai pro modal — pareamentos bem-sucedidos são silenciosos)
  const avisosVisiveis = avisos.filter(a => a.severidade === "warning" || a.severidade === "danger");
  const temAvisos = avisosVisiveis.length > 0;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[60] flex items-center justify-center bg-background/80 backdrop-blur-sm p-4"
    >
      <motion.div
        initial={{ scale: 0.95, y: 10 }}
        animate={{ scale: 1, y: 0 }}
        className="glass-card p-6 max-w-lg w-full"
      >
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            {temAvisos ? (
              <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-amber-500" />
              </div>
            ) : (
              <div className="w-10 h-10 rounded-xl bg-green-500/10 border border-green-500/30 flex items-center justify-center">
                <CheckCircle2 className="w-5 h-5 text-green-500" />
              </div>
            )}
            <div>
              <h3 className="text-lg font-semibold text-foreground">
                {temAvisos ? "CSV baixado com avisos" : "CSV baixado com sucesso"}
              </h3>
              {filename && (
                <p className="text-xs text-muted-foreground">{filename}</p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all"
            aria-label="Fechar"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-2 mb-4">
          <div className="bg-muted/30 rounded-lg p-3">
            <p className="text-xs text-muted-foreground mb-0.5">Total de dias</p>
            <p className="text-xl font-semibold text-foreground">{totalDias}</p>
          </div>
          <div className="bg-muted/30 rounded-lg p-3">
            <p className="text-xs text-muted-foreground mb-0.5">Plantões pareados</p>
            <p className="text-xl font-semibold text-green-500">{pareados}</p>
          </div>
          <div className="bg-muted/30 rounded-lg p-3">
            <p className="text-xs text-muted-foreground mb-0.5">Para revisar</p>
            <p className={`text-xl font-semibold ${temAvisos ? "text-amber-500" : "text-muted-foreground"}`}>
              {avisosVisiveis.length}
            </p>
          </div>
        </div>

        {/* Lista de avisos */}
        {temAvisos ? (
          <div className="border-t border-border/50 pt-4 mb-4 max-h-64 overflow-y-auto">
            <p className="text-sm font-medium text-foreground mb-3">Linhas para verificar no Excel</p>
            <div className="space-y-2">
              {avisosVisiveis.map((aviso, i) => (
                <div
                  key={i}
                  className="grid grid-cols-[100px_1fr] gap-3 py-2 border-b border-border/30 last:border-b-0"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        aviso.severidade === "danger" ? "bg-red-500" : "bg-amber-500"
                      }`}
                    />
                    <span className="text-sm font-mono text-foreground">{aviso.data}</span>
                  </div>
                  <span className="text-sm text-muted-foreground">{aviso.mensagem}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="border-t border-border/50 pt-4 mb-4">
            <p className="text-sm text-muted-foreground text-center">
              Nenhum aviso gerado. O sistema processou todas as marcações sem identificar inconsistências.
            </p>
          </div>
        )}

        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="px-6 py-2.5 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:opacity-90 transition-all"
          >
            OK, entendi
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
