// frontend/src/components/admin/AnnouncementFormModal.tsx
//
// Modal de criação/edição de aviso com preview ao vivo.

import { useState } from "react";
import { X, Loader2, Eye, Info, AlertTriangle, AlertOctagon, Sparkles } from "lucide-react";
import { toast } from "sonner";
import type { AdminAnnouncement } from "./AdminAnnouncementsTab";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function getToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("jwt_token");
}

const SEVERITIES = [
  { value: "info",     label: "🔵 Informação", allowsEverySession: false },
  { value: "warning",  label: "🟡 Aviso",      allowsEverySession: true  },
  { value: "critical", label: "🔴 Crítico",    allowsEverySession: true  },
  { value: "news",     label: "🟢 Novidade",   allowsEverySession: false },
];

const SEVERITY_PREVIEW = {
  info:     { icon: Info,          color: "text-blue-500",    bg: "bg-blue-500/15",    border: "border-blue-500/30",    label: "Informação" },
  warning:  { icon: AlertTriangle, color: "text-amber-500",   bg: "bg-amber-500/15",   border: "border-amber-500/30",   label: "Aviso" },
  critical: { icon: AlertOctagon,  color: "text-red-500",     bg: "bg-red-500/15",     border: "border-red-500/30",     label: "Crítico" },
  news:     { icon: Sparkles,      color: "text-emerald-500", bg: "bg-emerald-500/15", border: "border-emerald-500/30", label: "Novidade" },
};

interface Props {
  announcement?: AdminAnnouncement;
  onClose: () => void;
  onSaved: () => void;
}

const AnnouncementFormModal = ({ announcement, onClose, onSaved }: Props) => {
  const isEditing = !!announcement;

  const [form, setForm] = useState({
    title: announcement?.title ?? "",
    message: announcement?.message ?? "",
    severity: (announcement?.severity ?? "info") as "info" | "warning" | "critical" | "news",
    frequency: (announcement?.frequency ?? "once") as "once" | "every_session",
    priority: announcement?.priority ?? 100,
    active: announcement?.active ?? true,
    starts_at: dateToInput(announcement?.starts_at),
    ends_at: dateToInput(announcement?.ends_at),
  });

  const [saving, setSaving] = useState(false);

  const setField = <K extends keyof typeof form>(key: K, value: typeof form[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
  };

  // Severity controla quais frequencies são permitidas
  const allowsEverySession = ["warning", "critical"].includes(form.severity);

  // Se trocar pra info/news e estiver com every_session, força once
  const handleSeverityChange = (sev: typeof form.severity) => {
    setForm((f) => ({
      ...f,
      severity: sev,
      frequency: ["warning", "critical"].includes(sev) ? f.frequency : "once",
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim() || !form.message.trim()) {
      toast.error("Título e mensagem são obrigatórios.");
      return;
    }

    setSaving(true);
    try {
      const url = isEditing
        ? `/api/admin/announcements/${announcement!.id}`
        : "/api/admin/announcements";
      const method = isEditing ? "PUT" : "POST";

      const body = {
        title: form.title.trim(),
        message: form.message.trim(),
        severity: form.severity,
        frequency: form.frequency,
        priority: form.priority,
        active: form.active,
        starts_at: form.starts_at ? new Date(form.starts_at).toISOString() : null,
        ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null,
      };

      const token = getToken();
      const res = await fetch(`${API_BASE_URL}${url}`, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (res.ok) {
        toast.success(data.msg || "Salvo!");
        onSaved();
      } else {
        toast.error(data.msg || "Erro ao salvar.");
      }
    } catch {
      toast.error("Erro de rede.");
    } finally {
      setSaving(false);
    }
  };

  const previewSev = SEVERITY_PREVIEW[form.severity];
  const PreviewIcon = previewSev.icon;

  return (
    <div className="fixed inset-0 z-[90] bg-background/85 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-4xl max-h-[90vh] rounded-2xl bg-card border border-border/50 shadow-2xl overflow-hidden flex flex-col">

        {/* Header */}
        <div className="px-6 py-4 border-b border-border/50 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">
            {isEditing ? "Editar aviso" : "Novo aviso"}
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-muted/50 text-muted-foreground"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Conteúdo: form + preview */}
        <div className="flex-1 overflow-y-auto grid md:grid-cols-2 gap-0">

          {/* Form */}
          <form onSubmit={handleSubmit} className="p-6 space-y-4 border-r border-border/30">

            {/* Tipo */}
            <div>
              <label className="text-xs font-medium text-foreground mb-1 block">
                Tipo
              </label>
              <select
                value={form.severity}
                onChange={(e) => handleSeverityChange(e.target.value as typeof form.severity)}
                className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 outline-none focus:border-primary"
              >
                {SEVERITIES.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </div>

            {/* Título */}
            <div>
              <label className="text-xs font-medium text-foreground mb-1 block">
                Título *
              </label>
              <input
                type="text"
                value={form.title}
                onChange={(e) => setField("title", e.target.value)}
                maxLength={200}
                placeholder="Ex: Manutenção programada — domingo 02h às 04h"
                className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 outline-none focus:border-primary"
              />
              <div className="text-[10px] text-muted-foreground mt-0.5">
                {form.title.length}/200
              </div>
            </div>

            {/* Mensagem */}
            <div>
              <label className="text-xs font-medium text-foreground mb-1 block">
                Mensagem *
              </label>
              <textarea
                value={form.message}
                onChange={(e) => setField("message", e.target.value)}
                rows={4}
                placeholder="Descreva o que o usuário precisa saber. Quebras de linha são preservadas."
                className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 outline-none focus:border-primary resize-y"
              />
            </div>

            {/* Frequência */}
            <div>
              <label className="text-xs font-medium text-foreground mb-1 block">
                Frequência
              </label>
              <div className="space-y-2">
                <label className="flex items-start gap-2 p-2.5 rounded-md border border-border/50 hover:bg-muted/30 cursor-pointer">
                  <input
                    type="radio"
                    name="freq"
                    checked={form.frequency === "once"}
                    onChange={() => setField("frequency", "once")}
                    className="mt-0.5"
                  />
                  <div>
                    <div className="text-sm font-medium text-foreground">1× por usuário</div>
                    <div className="text-xs text-muted-foreground">
                      Após confirmar "Entendi", não aparece mais para esse usuário.
                    </div>
                  </div>
                </label>
                <label className={`flex items-start gap-2 p-2.5 rounded-md border cursor-pointer transition ${
                  allowsEverySession
                    ? "border-border/50 hover:bg-muted/30"
                    : "border-border/30 opacity-50 cursor-not-allowed"
                }`}>
                  <input
                    type="radio"
                    name="freq"
                    checked={form.frequency === "every_session"}
                    onChange={() => setField("frequency", "every_session")}
                    disabled={!allowsEverySession}
                    className="mt-0.5"
                  />
                  <div>
                    <div className="text-sm font-medium text-foreground">
                      Toda sessão
                      {!allowsEverySession && (
                        <span className="text-[10px] text-muted-foreground ml-2 font-normal">
                          (só Aviso/Crítico)
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Aparece em cada novo login até ser desativado.
                    </div>
                  </div>
                </label>
              </div>
            </div>

            {/* Janela de exibição */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-foreground mb-1 block">
                  Início (opcional)
                </label>
                <input
                  type="datetime-local"
                  value={form.starts_at}
                  onChange={(e) => setField("starts_at", e.target.value)}
                  className="w-full px-2 py-2 text-xs rounded-md bg-background border border-border/50 outline-none focus:border-primary"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-foreground mb-1 block">
                  Fim (opcional)
                </label>
                <input
                  type="datetime-local"
                  value={form.ends_at}
                  onChange={(e) => setField("ends_at", e.target.value)}
                  className="w-full px-2 py-2 text-xs rounded-md bg-background border border-border/50 outline-none focus:border-primary"
                />
              </div>
            </div>
            <p className="text-[10px] text-muted-foreground -mt-2">
              Sem início = começa imediatamente. Sem fim = fica ativo até pausar.
            </p>

            {/* Prioridade + Ativo */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-foreground mb-1 block">
                  Prioridade
                </label>
                <input
                  type="number"
                  value={form.priority}
                  onChange={(e) => setField("priority", parseInt(e.target.value) || 100)}
                  className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 outline-none focus:border-primary"
                />
                <div className="text-[10px] text-muted-foreground mt-0.5">
                  Menor = aparece primeiro
                </div>
              </div>
              <div>
                <label className="text-xs font-medium text-foreground mb-1 block">
                  Estado
                </label>
                <label className="flex items-center gap-2 p-2 rounded-md border border-border/50 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.active}
                    onChange={(e) => setField("active", e.target.checked)}
                  />
                  <span className="text-sm text-foreground">Ativo</span>
                </label>
              </div>
            </div>

            {/* Botões */}
            <div className="flex gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 px-4 py-2 text-sm rounded-md border border-border/50 hover:bg-muted/30 transition"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={saving}
                className="flex-1 gradient-primary text-primary-foreground px-4 py-2 text-sm font-semibold rounded-md flex items-center justify-center gap-2 hover:opacity-90 transition disabled:opacity-60"
              >
                {saving ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Salvando...</>
                ) : (
                  isEditing ? "Salvar alterações" : "Criar aviso"
                )}
              </button>
            </div>
          </form>

          {/* Preview ao vivo */}
          <div className="p-6 bg-muted/10">
            <div className="flex items-center gap-1.5 mb-3 text-xs text-muted-foreground">
              <Eye className="w-3.5 h-3.5" />
              Pré-visualização (como aparece para o usuário)
            </div>

            <div className={`rounded-2xl border-2 ${previewSev.border} bg-card overflow-hidden shadow-lg`}>
              <div className="px-5 pt-4 pb-2 flex items-center justify-between">
                <span className={`inline-flex items-center gap-1.5 ${previewSev.bg} ${previewSev.color} text-xs font-semibold px-2.5 py-1 rounded-full`}>
                  <PreviewIcon className="w-3.5 h-3.5" />
                  {previewSev.label}
                </span>
              </div>

              <div className="px-5 pb-2 flex justify-center">
                <div className={`w-14 h-14 rounded-2xl ${previewSev.bg} flex items-center justify-center`}>
                  <PreviewIcon className={`w-7 h-7 ${previewSev.color}`} />
                </div>
              </div>

              <div className="px-5 pb-4 text-center">
                <h3 className="text-lg font-bold text-foreground mb-2">
                  {form.title || "(título do aviso)"}
                </h3>
                <div className="text-sm text-muted-foreground leading-relaxed whitespace-pre-line">
                  {form.message || "(mensagem aparece aqui)"}
                </div>
              </div>

              <div className="border-t border-border/50" />
              <div className="p-3">
                <div className="w-full gradient-primary text-primary-foreground font-semibold py-2.5 rounded-lg text-center text-sm">
                  Entendi
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

function dateToInput(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return "";
  }
}

export default AnnouncementFormModal;
