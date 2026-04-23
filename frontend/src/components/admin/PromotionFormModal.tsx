// frontend/src/components/admin/PromotionFormModal.tsx
//
// Modal de criação/edição de promoção com preview ao vivo.
// Formulário à esquerda, preview usando PromotionCard à direita.

import { useState } from "react";
import { X, Loader2, Eye } from "lucide-react";
import { toast } from "sonner";
import PromotionCard from "@/components/PromotionCard";
import type { Promotion } from "@/hooks/usePromotions";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function getToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("jwt_token");
}

// Precisam estar sincronizados com os do backend (promotions_service.py)
const COLORS = ["emerald", "indigo", "amber", "rose", "blue", "violet", "teal", "slate"];
const ICONS = [
  "Sparkles", "Gift", "Zap", "Star", "Trophy", "Tag", "Percent",
  "Rocket", "Flame", "Heart", "Crown", "PartyPopper", "Megaphone",
  "Calendar", "TrendingUp", "Award", "ShieldCheck",
];

interface Props {
  promotion?: Promotion;
  onClose: () => void;
  onSaved: () => void;
}

const PromotionFormModal = ({ promotion, onClose, onSaved }: Props) => {
  const isEditing = !!promotion;

  const [form, setForm] = useState({
    title: promotion?.title ?? "",
    description: promotion?.description ?? "",
    badge_label: promotion?.badge_label ?? "Promoção",
    badge_color: promotion?.badge_color ?? "emerald",
    icon: promotion?.icon ?? "Sparkles",
    discount_hint: promotion?.discount_hint ?? "",
    cta_type: promotion?.cta_type ?? "none",
    cta_value: promotion?.cta_value ?? "",
    cta_label: promotion?.cta_label ?? "",
    priority: promotion?.priority ?? 100,
    active: promotion?.active ?? true,
    starts_at: dateToInput(promotion?.starts_at),
    ends_at: dateToInput(promotion?.ends_at),
  });

  const [saving, setSaving] = useState(false);

  const setField = <K extends keyof typeof form>(key: K, value: typeof form[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
  };

  // Preview: constrói um Promotion "fake" para passar ao card
  const previewPromotion: Promotion = {
    id: promotion?.id ?? -1,
    title: form.title || "(título da promoção)",
    description: form.description || "(descrição aparece aqui)",
    badge_label: form.badge_label,
    badge_color: form.badge_color,
    icon: form.icon,
    discount_hint: form.discount_hint || null,
    cta_type: form.cta_type as Promotion["cta_type"],
    cta_value: form.cta_value || null,
    cta_label: form.cta_label || null,
    priority: form.priority,
    active: form.active,
    starts_at: form.starts_at ? new Date(form.starts_at).toISOString() : null,
    ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null,
    status: "live",
    created_at: null,
    updated_at: null,
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim() || !form.description.trim()) {
      toast.error("Título e descrição são obrigatórios.");
      return;
    }
    if ((form.cta_type === "link" || form.cta_type === "code") && !form.cta_value.trim()) {
      toast.error("CTA requer um valor (URL ou código).");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        title: form.title.trim(),
        description: form.description.trim(),
        badge_label: form.badge_label.trim() || "Promoção",
        badge_color: form.badge_color,
        icon: form.icon,
        discount_hint: form.discount_hint.trim() || null,
        cta_type: form.cta_type,
        cta_value: form.cta_value.trim() || null,
        cta_label: form.cta_label.trim() || null,
        priority: Number(form.priority) || 100,
        active: form.active,
        starts_at: form.starts_at ? new Date(form.starts_at).toISOString() : null,
        ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null,
      };

      const url = isEditing
        ? `/api/admin/promotions/${promotion!.id}`
        : "/api/admin/promotions";
      const method = isEditing ? "PUT" : "POST";

      const token = getToken();
      const res = await fetch(`${API_BASE_URL}${url}`, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (res.ok) {
        toast.success(isEditing ? "Promoção atualizada." : "Promoção criada.");
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
    <div
      className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-card rounded-2xl w-full max-w-5xl my-8 overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border/50">
          <h3 className="text-lg font-semibold text-foreground">
            {isEditing ? "Editar promoção" : "Nova promoção"}
          </h3>
          <button
            onClick={onClose}
            className="p-1 text-muted-foreground hover:text-foreground"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Grid: formulário + preview */}
        <div className="grid md:grid-cols-[1fr_1fr] divide-y md:divide-y-0 md:divide-x divide-border/50">
          {/* FORMULÁRIO */}
          <form onSubmit={handleSubmit} className="p-6 max-h-[70vh] overflow-y-auto">
            <div className="space-y-4">
              <Field label="Título *">
                <input
                  type="text"
                  value={form.title}
                  onChange={(e) => setField("title", e.target.value)}
                  maxLength={200}
                  placeholder="Ex: Migre para o Premium até 30/abril"
                  className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 focus:border-primary outline-none"
                />
              </Field>

              <Field label="Descrição *">
                <textarea
                  value={form.description}
                  onChange={(e) => setField("description", e.target.value)}
                  rows={4}
                  placeholder="Descreva a promoção de forma clara..."
                  className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 focus:border-primary outline-none resize-y"
                />
              </Field>

              <div className="grid grid-cols-2 gap-3">
                <Field label="Badge (etiqueta)">
                  <input
                    type="text"
                    value={form.badge_label}
                    onChange={(e) => setField("badge_label", e.target.value)}
                    maxLength={50}
                    placeholder="Ex: Beta, Lançamento"
                    className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 focus:border-primary outline-none"
                  />
                </Field>

                <Field label="Hint (ex: 15% OFF)">
                  <input
                    type="text"
                    value={form.discount_hint}
                    onChange={(e) => setField("discount_hint", e.target.value)}
                    maxLength={60}
                    placeholder="Opcional"
                    className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 focus:border-primary outline-none"
                  />
                </Field>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <Field label="Cor">
                  <select
                    value={form.badge_color}
                    onChange={(e) => setField("badge_color", e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 focus:border-primary outline-none"
                  >
                    {COLORS.map((c) => (
                      <option key={c} value={c}>
                        {c.charAt(0).toUpperCase() + c.slice(1)}
                      </option>
                    ))}
                  </select>
                </Field>

                <Field label="Ícone">
                  <select
                    value={form.icon}
                    onChange={(e) => setField("icon", e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 focus:border-primary outline-none"
                  >
                    {ICONS.map((i) => (
                      <option key={i} value={i}>{i}</option>
                    ))}
                  </select>
                </Field>
              </div>

              {/* CTA */}
              <div className="pt-2 border-t border-border/30">
                <p className="text-xs font-semibold text-foreground uppercase tracking-wider mb-3">
                  Ação do card (CTA)
                </p>

                <Field label="Tipo">
                  <select
                    value={form.cta_type}
                    onChange={(e) => setField("cta_type", e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 focus:border-primary outline-none"
                  >
                    <option value="none">Nenhuma (só informativo)</option>
                    <option value="contact">Contato de suporte (WhatsApp + e-mail)</option>
                    <option value="link">Link externo ou interno</option>
                    <option value="code">Código promocional Stripe</option>
                  </select>
                </Field>

                {form.cta_type === "link" && (
                  <>
                    <Field label="URL ou caminho" small>
                      <input
                        type="text"
                        value={form.cta_value}
                        onChange={(e) => setField("cta_value", e.target.value)}
                        placeholder="/planos ou https://..."
                        className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 focus:border-primary outline-none"
                      />
                    </Field>
                    <Field label="Texto do botão" small>
                      <input
                        type="text"
                        value={form.cta_label}
                        onChange={(e) => setField("cta_label", e.target.value)}
                        placeholder="Ex: Ver planos"
                        className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 focus:border-primary outline-none"
                      />
                    </Field>
                  </>
                )}

                {form.cta_type === "code" && (
                  <>
                    <Field label="Código Stripe" small>
                      <input
                        type="text"
                        value={form.cta_value}
                        onChange={(e) => setField("cta_value", e.target.value.toUpperCase())}
                        placeholder="Ex: BF2026"
                        className="w-full px-3 py-2 text-sm font-mono rounded-md bg-background border border-border/50 focus:border-primary outline-none"
                      />
                      <p className="text-[11px] text-muted-foreground mt-1">
                        Crie o Promotion Code no Stripe Dashboard com este exato nome.
                      </p>
                    </Field>
                    <Field label="Texto acima do código" small>
                      <input
                        type="text"
                        value={form.cta_label}
                        onChange={(e) => setField("cta_label", e.target.value)}
                        placeholder="Ex: Use o código no checkout"
                        className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 focus:border-primary outline-none"
                      />
                    </Field>
                  </>
                )}
              </div>

              {/* Agendamento */}
              <div className="pt-2 border-t border-border/30">
                <p className="text-xs font-semibold text-foreground uppercase tracking-wider mb-3">
                  Agendamento
                </p>

                <div className="grid grid-cols-2 gap-3">
                  <Field label="Inicia em" small>
                    <input
                      type="datetime-local"
                      value={form.starts_at}
                      onChange={(e) => setField("starts_at", e.target.value)}
                      className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 focus:border-primary outline-none"
                    />
                    <p className="text-[11px] text-muted-foreground mt-1">
                      Vazio = ativa desde já
                    </p>
                  </Field>

                  <Field label="Termina em" small>
                    <input
                      type="datetime-local"
                      value={form.ends_at}
                      onChange={(e) => setField("ends_at", e.target.value)}
                      className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 focus:border-primary outline-none"
                    />
                    <p className="text-[11px] text-muted-foreground mt-1">
                      Vazio = sem expiração
                    </p>
                  </Field>
                </div>

                <div className="grid grid-cols-2 gap-3 mt-3">
                  <Field label="Prioridade" small>
                    <input
                      type="number"
                      value={form.priority}
                      onChange={(e) => setField("priority", Number(e.target.value))}
                      className="w-full px-3 py-2 text-sm rounded-md bg-background border border-border/50 focus:border-primary outline-none"
                    />
                    <p className="text-[11px] text-muted-foreground mt-1">
                      Menor = aparece primeiro
                    </p>
                  </Field>

                  <Field label="Ativa?" small>
                    <label className="flex items-center gap-2 py-2">
                      <input
                        type="checkbox"
                        checked={form.active}
                        onChange={(e) => setField("active", e.target.checked)}
                        className="w-4 h-4 rounded"
                      />
                      <span className="text-sm">
                        {form.active ? "Ativa" : "Pausada"}
                      </span>
                    </label>
                  </Field>
                </div>
              </div>
            </div>

            <div className="flex gap-2 mt-6 pt-4 border-t border-border/50 sticky bottom-0 bg-card">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 px-4 py-2 text-sm font-medium rounded-md border border-border/50 hover:bg-muted/50"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={saving}
                className="flex-1 px-4 py-2 text-sm font-medium rounded-md bg-foreground text-background hover:opacity-90 flex items-center justify-center gap-1.5 disabled:opacity-50"
              >
                {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                {isEditing ? "Salvar alterações" : "Criar promoção"}
              </button>
            </div>
          </form>

          {/* PREVIEW */}
          <div className="p-6 bg-muted/20 max-h-[70vh] overflow-y-auto">
            <div className="flex items-center gap-1.5 mb-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              <Eye className="w-3.5 h-3.5" />
              Preview ao vivo
            </div>

            <p className="text-xs text-muted-foreground mb-3">
              Como aparecerá no modal semanal e em /promocoes:
            </p>

            <PromotionCard
              promotion={previewPromotion}
              variant="modal"
              disableTracking
            />

            <div className="mt-4 p-3 rounded-lg bg-background border border-border/50 text-xs text-muted-foreground">
              <strong className="text-foreground">Dica:</strong> o card de indicação
              sempre aparece primeiro no modal. Esta promoção aparece
              abaixo dele, em ordem de prioridade.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

function Field({
  label, children, small = false,
}: { label: string; children: React.ReactNode; small?: boolean }) {
  return (
    <div className={small ? "mt-2" : ""}>
      <label className="text-xs font-medium text-foreground mb-1 block">
        {label}
      </label>
      {children}
    </div>
  );
}

function dateToInput(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    // YYYY-MM-DDTHH:mm (formato do input datetime-local)
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return "";
  }
}

export default PromotionFormModal;
