// frontend/src/components/admin/MaintenanceFormModal.tsx
//
// Modal para programar uma manutenção.
// Inclui opção de gerar aviso prévio automático.

import { useState } from "react";
import { X, Loader2, Wrench, Megaphone, Info } from "lucide-react";
import { toast } from "sonner";
import type { MaintenanceWindow } from "./AdminMaintenanceTab";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function getToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("jwt_token");
}

interface Props {
  maintenance?: MaintenanceWindow;
  onClose: () => void;
  onSaved: () => void;
}

const MaintenanceFormModal = ({ maintenance, onClose, onSaved }: Props) => {
  const isEditing = !!maintenance;

  const [form, setForm] = useState({
    starts_at: dateToInput(maintenance?.starts_at),
    ends_at: dateToInput(maintenance?.ends_at),
    message: maintenance?.message ?? "Estamos atualizando o sistema para você. Voltamos em breve.",
    create_announcement: !isEditing && true, // só ao criar, default true
    notice_hours_before: 48,
    announcement_title: "",
    announcement_message: "",
    advanced_announcement: false,
  });

  const [saving, setSaving] = useState(false);

  const setField = <K extends keyof typeof form>(key: K, value: typeof form[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
  };

  const computeDuration = () => {
    try {
      if (!form.starts_at || !form.ends_at) return "—";
      const start = new Date(form.starts_at);
      const end = new Date(form.ends_at);
      const minutes = Math.round((end.getTime() - start.getTime()) / 60000);
      if (minutes <= 0) return "inválido";
      if (minutes < 60) return `${minutes} min`;
      const h = Math.floor(minutes / 60);
      const min = minutes % 60;
      return `${h}h${min > 0 ? ` ${min}min` : ""}`;
    } catch {
      return "—";
    }
  };

  const computeNoticeStart = () => {
    try {
      if (!form.starts_at) return "—";
      const start = new Date(form.starts_at);
      const noticeStart = new Date(start.getTime() - form.notice_hours_before * 60 * 60 * 1000);
      const now = new Date();
      const actualStart = noticeStart < now ? now : noticeStart;
      return actualStart.toLocaleString("pt-BR", {
        day: "2-digit", month: "2-digit", year: "numeric",
        hour: "2-digit", minute: "2-digit",
      });
    } catch {
      return "—";
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!form.starts_at || !form.ends_at) {
      toast.error("Informe início e fim da manutenção.");
      return;
    }

    const start = new Date(form.starts_at);
    const end = new Date(form.ends_at);

    if (end <= start) {
      toast.error("Fim deve ser após o início.");
      return;
    }

    if (!form.message.trim()) {
      toast.error("Mensagem não pode ser vazia.");
      return;
    }

    setSaving(true);
    try {
      const url = isEditing
        ? `/api/admin/maintenance/${maintenance!.id}`
        : "/api/admin/maintenance";
      const method = isEditing ? "PATCH" : "POST";

      const body: Record<string, unknown> = {
        starts_at: start.toISOString(),
        ends_at: end.toISOString(),
        message: form.message.trim(),
      };

      // Só envia opções de aviso ao criar
      if (!isEditing) {
        body.create_announcement = form.create_announcement;
        if (form.create_announcement) {
          body.notice_hours_before = form.notice_hours_before;
          if (form.advanced_announcement) {
            if (form.announcement_title.trim()) {
              body.announcement_title = form.announcement_title.trim();
            }
            if (form.announcement_message.trim()) {
              body.announcement_message = form.announcement_message.trim();
            }
          }
        }
      }

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
        if (data.warning) {
          toast.warning(data.warning, { duration: 8000 });
        }
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

  return (
    <div className="fixed inset-0 z-[90] bg-background/85 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-2xl max-h-[90vh] rounded-2xl bg-card border border-border/50 shadow-2xl overflow-hidden flex flex-col">

        {/* Header */}
        <div className="px-6 py-4 border-b border-border/50 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <Wrench className="w-5 h-5 text-primary" />
            {isEditing ? "Editar manutenção" : "Programar manutenção"}
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md hover:bg-muted/50 text-muted-foreground"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-5">

          {/* Janela da manutenção */}
          <div>
            <h3 className="text-sm font-semibold text-foreground mb-2">
              Janela de manutenção
            </h3>
            <p className="text-xs text-muted-foreground mb-3">
              Período em que o sistema ficará bloqueado para usuários.
            </p>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-foreground mb-1 block">
                  Início *
                </label>
                <input
                  type="datetime-local"
                  value={form.starts_at}
                  onChange={(e) => setField("starts_at", e.target.value)}
                  required
                  className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 outline-none focus:border-primary"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-foreground mb-1 block">
                  Fim previsto *
                </label>
                <input
                  type="datetime-local"
                  value={form.ends_at}
                  onChange={(e) => setField("ends_at", e.target.value)}
                  required
                  className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 outline-none focus:border-primary"
                />
              </div>
            </div>

            <div className="mt-2 text-xs text-muted-foreground flex items-center gap-1.5">
              <Info className="w-3.5 h-3.5" />
              Duração: <strong className="text-foreground">{computeDuration()}</strong>
            </div>
          </div>

          {/* Mensagem na tela de bloqueio */}
          <div>
            <label className="text-sm font-semibold text-foreground mb-2 block">
              Mensagem na tela de bloqueio
            </label>
            <textarea
              value={form.message}
              onChange={(e) => setField("message", e.target.value)}
              rows={3}
              className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 outline-none focus:border-primary resize-y"
              placeholder="Mensagem que o usuário verá durante a manutenção"
            />
          </div>

          {/* Aviso prévio (só ao criar) */}
          {!isEditing && (
            <div className="border border-border/50 rounded-lg p-4 bg-muted/10">
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.create_announcement}
                  onChange={(e) => setField("create_announcement", e.target.checked)}
                  className="mt-0.5"
                />
                <div className="flex-1">
                  <div className="text-sm font-semibold text-foreground flex items-center gap-2">
                    <Megaphone className="w-4 h-4 text-blue-500" />
                    Criar aviso prévio automático
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    Gera um aviso (warning, every_session) que aparece para os usuários
                    antes da manutenção, lembrando do downtime.
                  </div>
                </div>
              </label>

              {form.create_announcement && (
                <div className="mt-4 ml-6 space-y-3">
                  <div>
                    <label className="text-xs font-medium text-foreground mb-1 block">
                      Antecedência (horas)
                    </label>
                    <select
                      value={form.notice_hours_before}
                      onChange={(e) => setField("notice_hours_before", parseInt(e.target.value))}
                      className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 outline-none focus:border-primary"
                    >
                      <option value={6}>6 horas antes</option>
                      <option value={12}>12 horas antes</option>
                      <option value={24}>24 horas antes (1 dia)</option>
                      <option value={48}>48 horas antes (2 dias)</option>
                      <option value={72}>72 horas antes (3 dias)</option>
                      <option value={168}>1 semana antes</option>
                    </select>
                    <div className="text-[11px] text-muted-foreground mt-1">
                      Aviso começará: <strong className="text-foreground">{computeNoticeStart()}</strong>
                      {" "}até início da manutenção
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => setField("advanced_announcement", !form.advanced_announcement)}
                    className="text-xs text-primary hover:underline"
                  >
                    {form.advanced_announcement
                      ? "− Ocultar título e mensagem personalizados"
                      : "+ Personalizar título e mensagem do aviso"}
                  </button>

                  {form.advanced_announcement && (
                    <div className="space-y-2 pt-1">
                      <div>
                        <label className="text-xs font-medium text-foreground mb-1 block">
                          Título do aviso (opcional)
                        </label>
                        <input
                          type="text"
                          value={form.announcement_title}
                          onChange={(e) => setField("announcement_title", e.target.value)}
                          placeholder="Deixe vazio para usar título padrão automático"
                          maxLength={200}
                          className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 outline-none focus:border-primary"
                        />
                      </div>
                      <div>
                        <label className="text-xs font-medium text-foreground mb-1 block">
                          Mensagem do aviso (opcional)
                        </label>
                        <textarea
                          value={form.announcement_message}
                          onChange={(e) => setField("announcement_message", e.target.value)}
                          placeholder="Deixe vazio para usar mensagem padrão"
                          rows={3}
                          className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 outline-none focus:border-primary resize-y"
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Aviso de edição */}
          {isEditing && maintenance?.announcement && (
            <div className="border border-blue-500/30 rounded-lg p-3 bg-blue-500/5 text-xs text-muted-foreground flex items-start gap-2">
              <Megaphone className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" />
              <div>
                Esta manutenção tem um <strong>aviso prévio</strong> vinculado:
                "{maintenance.announcement.title}".
                <br />
                Edite o aviso separadamente na aba <strong>Avisos</strong>.
              </div>
            </div>
          )}

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
                isEditing ? "Salvar alterações" : "Programar manutenção"
              )}
            </button>
          </div>
        </form>
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

export default MaintenanceFormModal;
