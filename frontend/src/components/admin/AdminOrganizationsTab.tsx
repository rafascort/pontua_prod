// frontend/src/components/admin/AdminOrganizationsTab.tsx
import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import {
  Building, Plus, Users, ChevronLeft, ChevronRight, CreditCard,
  Pencil, Pause, Play, Trash2, UserPlus, ExternalLink, Crown,
  Copy, RefreshCw, X, AlertCircle, MoreVertical, Check, ShoppingCart,
} from "lucide-react";

// ═══════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════
interface Organization {
  id: number;
  name: string;
  legal_name: string | null;
  cnpj: string | null;
  billing_email: string;
  is_active: boolean;
  plan_status: string;
  price_per_page_cents: number;
  pending_price_per_page_cents: number | null;
  page_count: number;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  stripe_price_id: string | null;
  next_reset_date: string | null;
  created_at: string | null;
  member_count?: number;
  estimated_invoice_cents?: number;
  estimated_invoice_brl?: number;
}

interface Member {
  id: number;
  email: string;
  is_active: boolean;
  org_role: string | null;
  can_process: boolean;
  page_count: number;
  plan_status_legacy: string;
}

// ═══════════════════════════════════════════════════════════════════
// API
// ═══════════════════════════════════════════════════════════════════
const authHeaders = () => ({
  Authorization: `Bearer ${localStorage.getItem("access_token")}`,
  "Content-Type": "application/json",
});

async function apiCall(url: string, opts: RequestInit = {}) {
  const r = await fetch(url, { ...opts, headers: { ...authHeaders(), ...opts.headers } });
  let data: any = {};
  try { data = await r.json(); } catch {}
  return { ok: r.ok, status: r.status, data };
}

const api = {
  list:         ()              => apiCall("/api/admin/organizations"),
  get:          (id: number)    => apiCall(`/api/admin/organizations/${id}`),
  create:       (b: any)        => apiCall("/api/admin/organizations", { method: "POST",  body: JSON.stringify(b) }),
  update:       (id: number, b: any) => apiCall(`/api/admin/organizations/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
  setStatus:    (id: number, action: "suspend" | "reactivate") => apiCall(`/api/admin/organizations/${id}/status`, { method: "PATCH", body: JSON.stringify({ action }) }),
  addMember:    (id: number, b: any) => apiCall(`/api/admin/organizations/${id}/members`, { method: "POST",  body: JSON.stringify(b) }),
  updateMember: (id: number, uid: number, b: any) => apiCall(`/api/admin/organizations/${id}/members/${uid}`, { method: "PATCH", body: JSON.stringify(b) }),
  removeMember: (id: number, uid: number) => apiCall(`/api/admin/organizations/${id}/members/${uid}`, { method: "DELETE" }),
  createCheckout: (id: number)  => apiCall(`/api/admin/organizations/${id}/checkout-session`, { method: "POST" }),
};

// ═══════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════
const INPUT_CLS = "w-full bg-muted/30 border border-border/50 rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary transition-colors";

const formatBRL = (cents: number) =>
  `R$ ${(cents / 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const formatCNPJ = (raw: string | null) => {
  if (!raw) return "—";
  const d = raw.replace(/\D/g, "");
  if (d.length !== 14) return raw;
  return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
};

const statusBadge = (status: string) => {
  const map: Record<string, { label: string; cls: string }> = {
    awaiting_setup: { label: "AGUARDANDO CARTÃO", cls: "bg-amber-500/15 text-amber-300" },
    active:         { label: "ATIVA",              cls: "bg-emerald-500/15 text-emerald-300" },
    past_due:       { label: "PAGAMENTO PENDENTE", cls: "bg-red-500/15 text-red-300" },
    suspended:      { label: "SUSPENSA",           cls: "bg-slate-500/15 text-slate-300" },
    inactive:       { label: "INATIVA",            cls: "bg-slate-500/15 text-slate-400" },
  };
  return map[status] || { label: status.toUpperCase(), cls: "bg-slate-500/15 text-slate-300" };
};

const orgInitials = (name: string) => {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
};

// ═══════════════════════════════════════════════════════════════════
// MAIN COMPONENT (lista + detail)
// ═══════════════════════════════════════════════════════════════════
export default function AdminOrganizationsTab() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const { ok, data } = await api.list();
      if (ok) setOrgs(data.organizations || []);
      else toast.error(data.msg || "Erro ao listar empresas.");
    } catch { toast.error("Erro de rede."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchList(); }, [fetchList]);

  if (selectedId !== null) {
    return (
      <OrganizationDetail
        orgId={selectedId}
        onBack={() => { setSelectedId(null); fetchList(); }}
      />
    );
  }

  const totMembers = orgs.reduce((s, o) => s + (o.member_count || 0), 0);
  const totPages   = orgs.reduce((s, o) => s + o.page_count, 0);
  const totBRL     = orgs.reduce((s, o) => s + (o.estimated_invoice_brl || 0), 0);

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Empresas"            value={orgs.length} />
        <StatCard label="Funcionários"        value={totMembers} />
        <StatCard label="Págs no ciclo"       value={totPages.toLocaleString("pt-BR")} />
        <StatCard label="A faturar"           value={`R$ ${totBRL.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} />
      </div>

      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-foreground font-semibold text-lg">Empresas cadastradas</h3>
          <p className="text-muted-foreground text-xs mt-1">Escritórios e perícias parceiras</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg gradient-primary text-primary-foreground text-sm font-medium hover:shadow-lg transition-all"
        >
          <Plus className="w-4 h-4" /> Nova empresa
        </button>
      </div>

      <div className="rounded-xl border border-border/50 bg-card/30 overflow-hidden">
        {loading && orgs.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground text-sm">Carregando...</div>
        ) : orgs.length === 0 ? (
          <div className="p-12 text-center">
            <Building className="w-12 h-12 mx-auto text-muted-foreground/40 mb-3" />
            <p className="text-foreground font-medium">Nenhuma empresa cadastrada</p>
            <p className="text-muted-foreground text-sm mt-1">Clique em "Nova empresa" para começar.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/30 text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="text-left  px-4 py-3 font-medium">Empresa</th>
                  <th className="text-left  px-4 py-3 font-medium">CNPJ</th>
                  <th className="text-right px-4 py-3 font-medium">R$/pág</th>
                  <th className="text-right px-4 py-3 font-medium">Func.</th>
                  <th className="text-right px-4 py-3 font-medium">Págs</th>
                  <th className="text-right px-4 py-3 font-medium">A faturar</th>
                  <th className="text-center px-4 py-3 font-medium">Status</th>
                  <th className="w-8"></th>
                </tr>
              </thead>
              <tbody>
                {orgs.map(org => {
                  const badge = statusBadge(org.plan_status);
                  return (
                    <tr
                      key={org.id}
                      onClick={() => setSelectedId(org.id)}
                      className="border-t border-border/30 cursor-pointer hover:bg-muted/20 transition-colors"
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-md gradient-primary text-primary-foreground flex items-center justify-center text-xs font-semibold">
                            {orgInitials(org.name)}
                          </div>
                          <div>
                            <div className="text-foreground font-medium">{org.name}</div>
                            <div className="text-muted-foreground text-xs">{org.billing_email}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground text-xs">{formatCNPJ(org.cnpj)}</td>
                      <td className="px-4 py-3 text-right">
                        {formatBRL(org.price_per_page_cents)}
                        {org.pending_price_per_page_cents && (
                          <div className="text-amber-400 text-xs mt-0.5">→ {formatBRL(org.pending_price_per_page_cents)}</div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">{org.member_count || 0}</td>
                      <td className="px-4 py-3 text-right">{org.page_count.toLocaleString("pt-BR")}</td>
                      <td className="px-4 py-3 text-right text-foreground font-medium">{formatBRL(org.estimated_invoice_cents || 0)}</td>
                      <td className="px-4 py-3 text-center">
                        <span className={`text-[10px] px-2 py-0.5 rounded-md ${badge.cls}`}>{badge.label}</span>
                      </td>
                      <td className="px-2 py-3 text-muted-foreground"><ChevronRight className="w-4 h-4" /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showCreate && (
        <CreateOrgModal
          onClose={() => setShowCreate(false)}
          onSuccess={(newId) => { setShowCreate(false); fetchList(); if (newId) setSelectedId(newId); }}
        />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// STAT CARD
// ═══════════════════════════════════════════════════════════════════
function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-card/30 border border-border/30 p-3">
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="text-foreground text-xl font-semibold mt-1">{value}</div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// DETAIL VIEW
// ═══════════════════════════════════════════════════════════════════
function OrganizationDetail({ orgId, onBack }: { orgId: number; onBack: () => void }) {
  const [org, setOrg] = useState<Organization | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [showEdit, setShowEdit] = useState(false);
  const [showAddMember, setShowAddMember] = useState(false);
  const [confirmStatus, setConfirmStatus] = useState(false);
  const [busy, setBusy] = useState(false);

  const fetch_ = useCallback(async () => {
    setLoading(true);
    try {
      const { ok, data } = await api.get(orgId);
      if (ok) { setOrg(data.organization); setMembers(data.members || []); }
      else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setLoading(false); }
  }, [orgId]);

  useEffect(() => { fetch_(); }, [fetch_]);

  const toggleStatus = async () => {
    if (!org) return;
    setBusy(true);
    try {
      const action = org.is_active ? "suspend" : "reactivate";
      const { ok, data } = await api.setStatus(orgId, action);
      if (ok) { toast.success(data.msg); setConfirmStatus(false); fetch_(); }
      else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setBusy(false); }
  };

  const genCheckout = async () => {
    setBusy(true);
    try {
      const { ok, data } = await api.createCheckout(orgId);
      if (ok && data.url) {
        window.open(data.url, "_blank");
        try { await navigator.clipboard.writeText(data.url); } catch {}
        toast.success("Checkout aberto em nova aba. URL copiada para a área de transferência.");
      } else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setBusy(false); }
  };

  if (loading) return <div className="p-8 text-center text-muted-foreground text-sm">Carregando...</div>;
  if (!org) {
    return (
      <div className="space-y-4">
        <button onClick={onBack} className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
          <ChevronLeft className="w-4 h-4" /> Voltar
        </button>
        <div className="text-center p-8 text-muted-foreground">Empresa não encontrada.</div>
      </div>
    );
  }

  const badge = statusBadge(org.plan_status);
  const cents = (org.page_count || 0) * (org.price_per_page_cents || 0);

  return (
    <div className="space-y-5">
      <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
        <ChevronLeft className="w-4 h-4" /> Voltar para empresas
      </button>

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-lg gradient-primary text-primary-foreground flex items-center justify-center text-sm font-semibold">
            {orgInitials(org.name)}
          </div>
          <div>
            <h3 className="text-foreground text-xl font-semibold">{org.name}</h3>
            <p className="text-muted-foreground text-xs mt-0.5">
              CNPJ {formatCNPJ(org.cnpj)} · ID #{org.id} · {org.created_at ? `Criada ${new Date(org.created_at).toLocaleDateString("pt-BR")}` : ""}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-[10px] px-2 py-1 rounded-md ${badge.cls}`}>{badge.label}</span>
          <button onClick={() => setShowEdit(true)} className="px-3 py-1.5 rounded-md border border-border/50 text-muted-foreground hover:text-foreground hover:border-border text-xs flex items-center gap-1.5 transition-all">
            <Pencil className="w-3 h-3" /> Editar
          </button>
          <button onClick={() => setConfirmStatus(true)} className={`px-3 py-1.5 rounded-md border text-xs flex items-center gap-1.5 transition-all ${
            org.is_active ? "border-amber-500/30 text-amber-300 hover:bg-amber-500/10"
                          : "border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/10"
          }`}>
            {org.is_active ? <><Pause className="w-3 h-3" /> Suspender</> : <><Play className="w-3 h-3" /> Reativar</>}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Preço/pág"     value={formatBRL(org.price_per_page_cents)} />
        <StatCard label="Pág. no ciclo" value={org.page_count.toLocaleString("pt-BR")} />
        <StatCard label="A faturar"     value={formatBRL(cents)} />
        <StatCard label="Próx. fatura"  value={org.next_reset_date ? new Date(org.next_reset_date).toLocaleDateString("pt-BR") : "—"} />
      </div>

      {org.pending_price_per_page_cents && (
        <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 px-4 py-3 text-amber-200 text-sm flex items-start gap-3">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>Mudança de preço agendada: <span className="font-medium">{formatBRL(org.pending_price_per_page_cents)}</span> a partir do próximo ciclo (atual: {formatBRL(org.price_per_page_cents)}).</div>
        </div>
      )}

      {/* Membros */}
      <div className="rounded-xl border border-border/50 bg-card/30 overflow-hidden">
        <div className="px-4 py-3 border-b border-border/30 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-muted-foreground" />
            <span className="text-foreground font-medium text-sm">Membros ({members.length})</span>
          </div>
          <button onClick={() => setShowAddMember(true)} className="px-3 py-1.5 rounded-md gradient-primary text-primary-foreground text-xs flex items-center gap-1.5 hover:shadow-lg transition-all">
            <UserPlus className="w-3 h-3" /> Adicionar
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-muted-foreground bg-muted/20">
              <tr>
                <th className="text-left  px-4 py-2 font-medium">E-mail</th>
                <th className="text-left  px-4 py-2 font-medium">Papel</th>
                <th className="text-right px-4 py-2 font-medium">Págs</th>
                <th className="text-center px-4 py-2 font-medium">Ativo</th>
                <th className="w-12"></th>
              </tr>
            </thead>
            <tbody>
              {members.map(m => (
                <MemberRow key={m.id} member={m} orgId={orgId} onChange={fetch_} />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Stripe */}
      <div className="rounded-xl border border-border/50 bg-card/30 p-4">
        <div className="flex items-center gap-2 mb-3">
          <CreditCard className="w-4 h-4 text-muted-foreground" />
          <span className="text-foreground font-medium text-sm">Faturamento Stripe</span>
        </div>
        {org.stripe_customer_id ? (
          <div className="space-y-2 text-sm">
            <KeyValue label="Customer"     value={org.stripe_customer_id} copyable />
            <KeyValue label="Subscription" value={org.stripe_subscription_id || "—"} copyable={!!org.stripe_subscription_id} />
            <KeyValue label="Price atual"  value={org.stripe_price_id || "—"} copyable={!!org.stripe_price_id} />
            <div className="pt-2">
              <a
                href={`https://dashboard.stripe.com/customers/${org.stripe_customer_id}`}
                target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-border/50 hover:border-border text-muted-foreground hover:text-foreground transition-all"
              >
                <ExternalLink className="w-3 h-3" /> Abrir no Stripe Dashboard
              </a>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-muted-foreground text-sm">
              Esta empresa ainda não tem cartão cadastrado. Gere um link de checkout e envie para o admin da empresa.
            </p>
            <button
              onClick={genCheckout}
              disabled={busy}
              className="px-3 py-2 rounded-md gradient-primary text-primary-foreground text-sm flex items-center gap-2 hover:shadow-lg transition-all disabled:opacity-50"
            >
              <ShoppingCart className="w-4 h-4" />
              {busy ? "Gerando…" : "Gerar link de checkout"}
            </button>
          </div>
        )}
      </div>

      {showEdit && (
        <EditOrgModal org={org} onClose={() => setShowEdit(false)} onSuccess={() => { setShowEdit(false); fetch_(); }} />
      )}
      {showAddMember && (
        <AddMemberModal orgId={orgId} onClose={() => setShowAddMember(false)} onSuccess={() => { setShowAddMember(false); fetch_(); }} />
      )}
      {confirmStatus && (
        <ConfirmDialog
          title={org.is_active ? "Suspender empresa?" : "Reativar empresa?"}
          message={org.is_active
            ? `Todos os ${members.length} funcionários ficarão bloqueados de processar PDFs imediatamente.`
            : `A empresa voltará a poder processar PDFs.`}
          confirmLabel={org.is_active ? "Suspender" : "Reativar"}
          danger={org.is_active}
          loading={busy}
          onCancel={() => setConfirmStatus(false)}
          onConfirm={toggleStatus}
        />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// MEMBER ROW
// ═══════════════════════════════════════════════════════════════════
function MemberRow({ member, orgId, onChange }: { member: Member; orgId: number; onChange: () => void }) {
  const [menu, setMenu] = useState(false);
  const [busy, setBusy] = useState(false);
  const isAdmin = member.org_role === "admin";

  const update = async (b: any) => {
    setBusy(true);
    try {
      const { ok, data } = await api.updateMember(orgId, member.id, b);
      if (ok) { toast.success(data.msg || "Atualizado."); onChange(); }
      else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setBusy(false); setMenu(false); }
  };

  const remove = async () => {
    if (!confirm(`Remover ${member.email} da empresa? Ele voltará a ser usuário avulso.`)) return;
    setBusy(true);
    try {
      const { ok, data } = await api.removeMember(orgId, member.id);
      if (ok) { toast.success("Removido."); onChange(); }
      else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setBusy(false); setMenu(false); }
  };

  return (
    <tr className="border-t border-border/30 relative">
      <td className="px-4 py-3 text-foreground">{member.email}</td>
      <td className="px-4 py-3">
        {isAdmin ? (
          <span className="text-xs px-2 py-0.5 rounded-md bg-primary/15 text-primary inline-flex items-center gap-1">
            <Crown className="w-3 h-3" /> ADMIN
          </span>
        ) : (
          <span className="text-xs px-2 py-0.5 rounded-md bg-muted/30 text-muted-foreground">MEMBRO</span>
        )}
        {isAdmin && !member.can_process && (
          <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300">só financeiro</span>
        )}
      </td>
      <td className="px-4 py-3 text-right text-muted-foreground">{member.page_count.toLocaleString("pt-BR")}</td>
      <td className="px-4 py-3 text-center">
        {member.is_active
          ? <Check className="w-4 h-4 text-emerald-400 mx-auto" />
          : <X     className="w-4 h-4 text-muted-foreground/50 mx-auto" />}
      </td>
      <td className="px-2 py-3 text-right">
        <button onClick={() => setMenu(o => !o)} className="p-1 rounded hover:bg-muted/30 text-muted-foreground">
          <MoreVertical className="w-4 h-4" />
        </button>
        {menu && (
          <>
            <div className="fixed inset-0 z-30" onClick={() => setMenu(false)} />
            <div className="absolute right-4 mt-1 w-56 rounded-lg border border-border/50 bg-card shadow-xl z-40 py-1 text-left text-sm">
              {!isAdmin && (
                <button onClick={() => update({ org_role: "admin" })} disabled={busy} className="w-full px-3 py-2 hover:bg-muted/30 flex items-center gap-2 text-foreground">
                  <Crown className="w-4 h-4 text-primary" /> Promover a admin
                </button>
              )}
              {isAdmin && (
                <>
                  <button onClick={() => update({ org_role: "member" })} disabled={busy} className="w-full px-3 py-2 hover:bg-muted/30 flex items-center gap-2 text-foreground">
                    <Users className="w-4 h-4 text-muted-foreground" /> Rebaixar a membro
                  </button>
                  <button onClick={() => update({ can_process: !member.can_process })} disabled={busy} className="w-full px-3 py-2 hover:bg-muted/30 flex items-center gap-2 text-foreground">
                    <RefreshCw className="w-4 h-4 text-muted-foreground" />
                    {member.can_process ? "Desligar processamento" : "Ligar processamento"}
                  </button>
                </>
              )}
              <button onClick={() => update({ is_active: !member.is_active })} disabled={busy} className="w-full px-3 py-2 hover:bg-muted/30 flex items-center gap-2 text-foreground">
                {member.is_active
                  ? <><Pause className="w-4 h-4 text-amber-400" /> Desativar</>
                  : <><Play  className="w-4 h-4 text-emerald-400" /> Ativar</>}
              </button>
              <div className="border-t border-border/30 my-1" />
              <button onClick={remove} disabled={busy} className="w-full px-3 py-2 hover:bg-destructive/10 flex items-center gap-2 text-destructive">
                <Trash2 className="w-4 h-4" /> Remover da empresa
              </button>
            </div>
          </>
        )}
      </td>
    </tr>
  );
}

// ═══════════════════════════════════════════════════════════════════
// KEY-VALUE LINHA
// ═══════════════════════════════════════════════════════════════════
function KeyValue({ label, value, copyable }: { label: string; value: string; copyable?: boolean }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-center justify-between gap-3 text-xs">
      <span className="text-muted-foreground shrink-0">{label}</span>
      <div className="flex items-center gap-1.5 min-w-0">
        <code className="text-foreground font-mono truncate">{value}</code>
        {copyable && value !== "—" && (
          <button
            onClick={async () => { try { await navigator.clipboard.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch {} }}
            className="text-muted-foreground hover:text-foreground p-1"
            title="Copiar"
          >
            {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
          </button>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// MODAL SHELL & FIELD
// ═══════════════════════════════════════════════════════════════════
function ModalShell({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-lg bg-card border border-border rounded-xl shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="px-5 py-4 border-b border-border/30 flex items-center justify-between">
          <h4 className="font-semibold text-foreground">{title}</h4>
          <button onClick={onClose} className="p-1 text-muted-foreground hover:text-foreground rounded">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs text-muted-foreground mb-1">{label}</label>
      {children}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// CREATE ORG MODAL
// ═══════════════════════════════════════════════════════════════════
function CreateOrgModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: (newId: number) => void }) {
  const [form, setForm] = useState({
    name: "", legal_name: "", cnpj: "", billing_email: "",
    price_per_page_cents: 62, admin_email: "", admin_can_process: true,
  });
  const [busy, setBusy] = useState(false);
  const [invite, setInvite] = useState<string | null>(null);
  const [newId, setNewId] = useState<number | null>(null);

  const submit = async () => {
    if (!form.name || !form.billing_email || !form.admin_email) {
      toast.error("Preencha nome, e-mail de cobrança e e-mail do admin."); return;
    }
    setBusy(true);
    try {
      const { ok, data } = await api.create(form);
      if (ok) {
        toast.success("Empresa criada!");
        setNewId(data.organization?.id || 0);
        if (data.invite_link) setInvite(data.invite_link);
        else onSuccess(data.organization?.id || 0);
      } else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setBusy(false); }
  };

  if (invite) {
    return (
      <ModalShell title="Empresa criada — envie o link" onClose={() => onSuccess(newId || 0)}>
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            O admin da empresa precisa abrir este link para definir senha e cadastrar o cartão. Envie por e-mail/WhatsApp.
          </p>
          <div className="rounded-lg bg-muted/30 border border-border/50 p-3 flex items-center gap-2">
            <code className="text-xs text-foreground font-mono truncate flex-1">{invite}</code>
            <button onClick={() => { navigator.clipboard.writeText(invite); toast.success("Link copiado!"); }}
                    className="text-xs px-2 py-1 rounded border border-border/50 hover:border-border text-foreground">
              <Copy className="w-3 h-3" />
            </button>
          </div>
          <div className="flex justify-end">
            <button onClick={() => onSuccess(newId || 0)} className="px-4 py-2 rounded-lg gradient-primary text-primary-foreground text-sm">
              Concluir
            </button>
          </div>
        </div>
      </ModalShell>
    );
  }

  return (
    <ModalShell title="Nova empresa" onClose={onClose}>
      <div className="space-y-4">
        <div className="text-xs uppercase tracking-wider text-muted-foreground">Dados da empresa</div>
        <Field label="Nome fantasia *">
          <input type="text" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className={INPUT_CLS} placeholder="Pereira & Garcia Perícia Contábil" />
        </Field>
        <Field label="Razão social">
          <input type="text" value={form.legal_name} onChange={e => setForm({ ...form, legal_name: e.target.value })} className={INPUT_CLS} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="CNPJ">
            <input type="text" value={form.cnpj} onChange={e => setForm({ ...form, cnpj: e.target.value })} className={INPUT_CLS} placeholder="00.000.000/0000-00" />
          </Field>
          <Field label="E-mail de cobrança *">
            <input type="email" value={form.billing_email} onChange={e => setForm({ ...form, billing_email: e.target.value })} className={INPUT_CLS} placeholder="financeiro@empresa.com.br" />
          </Field>
        </div>
        <Field label="Preço por página (centavos) *">
          <input type="number" min={1} max={10000} value={form.price_per_page_cents} onChange={e => setForm({ ...form, price_per_page_cents: Number(e.target.value) })} className={INPUT_CLS} />
          <div className="text-xs text-muted-foreground mt-1">
            R$ {(form.price_per_page_cents / 100).toFixed(2).replace(".", ",")} por página · valor combinado, sem mínimo mensal
          </div>
        </Field>
        <div className="text-xs uppercase tracking-wider text-muted-foreground pt-2">Admin da empresa (1º usuário)</div>
        <Field label="E-mail do admin *">
          <input type="email" value={form.admin_email} onChange={e => setForm({ ...form, admin_email: e.target.value })} className={INPUT_CLS} placeholder="admin@empresa.com.br" />
        </Field>
        <label className="flex items-center gap-2 text-sm text-foreground">
          <input type="checkbox" checked={form.admin_can_process} onChange={e => setForm({ ...form, admin_can_process: e.target.checked })} className="rounded" />
          Admin também pode processar PDFs (recomendado)
        </label>
        <div className="flex justify-end gap-2 pt-3 border-t border-border/30">
          <button onClick={onClose} disabled={busy} className="px-4 py-2 rounded-lg border border-border/50 text-muted-foreground hover:text-foreground text-sm">Cancelar</button>
          <button onClick={submit} disabled={busy} className="px-4 py-2 rounded-lg gradient-primary text-primary-foreground text-sm font-medium disabled:opacity-50">
            {busy ? "Criando…" : "Criar empresa"}
          </button>
        </div>
      </div>
    </ModalShell>
  );
}

// ═══════════════════════════════════════════════════════════════════
// EDIT ORG MODAL
// ═══════════════════════════════════════════════════════════════════
function EditOrgModal({ org, onClose, onSuccess }: { org: Organization; onClose: () => void; onSuccess: () => void }) {
  const [form, setForm] = useState({
    name: org.name,
    legal_name: org.legal_name || "",
    cnpj: org.cnpj || "",
    billing_email: org.billing_email,
    price_per_page_cents: org.pending_price_per_page_cents ?? org.price_per_page_cents,
  });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const { ok, data } = await api.update(org.id, form);
      if (ok) { toast.success(data.msg || "Atualizado."); onSuccess(); }
      else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setBusy(false); }
  };
  const pricePending = form.price_per_page_cents !== org.price_per_page_cents;
  return (
    <ModalShell title={`Editar empresa #${org.id}`} onClose={onClose}>
      <div className="space-y-4">
        <Field label="Nome fantasia *"><input type="text" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className={INPUT_CLS} /></Field>
        <Field label="Razão social"><input type="text" value={form.legal_name} onChange={e => setForm({ ...form, legal_name: e.target.value })} className={INPUT_CLS} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="CNPJ"><input type="text" value={form.cnpj} onChange={e => setForm({ ...form, cnpj: e.target.value })} className={INPUT_CLS} /></Field>
          <Field label="E-mail de cobrança"><input type="email" value={form.billing_email} onChange={e => setForm({ ...form, billing_email: e.target.value })} className={INPUT_CLS} /></Field>
        </div>
        <Field label="Preço por página (centavos)">
          <input type="number" min={1} max={10000} value={form.price_per_page_cents} onChange={e => setForm({ ...form, price_per_page_cents: Number(e.target.value) })} className={INPUT_CLS} />
          <div className="text-xs text-muted-foreground mt-1">
            R$ {(form.price_per_page_cents / 100).toFixed(2).replace(".", ",")} por página
            {pricePending && <span className="text-amber-400"> — só passa a valer no próximo ciclo de cobrança</span>}
          </div>
        </Field>
        <div className="flex justify-end gap-2 pt-3 border-t border-border/30">
          <button onClick={onClose} disabled={busy} className="px-4 py-2 rounded-lg border border-border/50 text-muted-foreground hover:text-foreground text-sm">Cancelar</button>
          <button onClick={submit} disabled={busy} className="px-4 py-2 rounded-lg gradient-primary text-primary-foreground text-sm font-medium disabled:opacity-50">{busy ? "Salvando…" : "Salvar"}</button>
        </div>
      </div>
    </ModalShell>
  );
}

// ═══════════════════════════════════════════════════════════════════
// ADD MEMBER MODAL
// ═══════════════════════════════════════════════════════════════════
function AddMemberModal({ orgId, onClose, onSuccess }: { orgId: number; onClose: () => void; onSuccess: () => void }) {
  const [form, setForm] = useState({ email: "", role: "member" as "admin" | "member", can_process: true });
  const [busy, setBusy] = useState(false);
  const [invite, setInvite] = useState<string | null>(null);
  const submit = async () => {
    if (!form.email) { toast.error("Informe o e-mail."); return; }
    setBusy(true);
    try {
      const { ok, data } = await api.addMember(orgId, form);
      if (ok) {
        if (data.invite_link) setInvite(data.invite_link);
        else { toast.success(`Membro ${data.was_migrated ? "migrado" : "adicionado"}.`); onSuccess(); }
      } else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setBusy(false); }
  };
  if (invite) {
    return (
      <ModalShell title="Membro adicionado — envie o link" onClose={onSuccess}>
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">O novo membro precisa abrir este link para definir a senha.</p>
          <div className="rounded-lg bg-muted/30 border border-border/50 p-3 flex items-center gap-2">
            <code className="text-xs text-foreground font-mono truncate flex-1">{invite}</code>
            <button onClick={() => { navigator.clipboard.writeText(invite); toast.success("Copiado!"); }}
                    className="text-xs px-2 py-1 rounded border border-border/50 hover:border-border text-foreground">
              <Copy className="w-3 h-3" />
            </button>
          </div>
          <div className="flex justify-end">
            <button onClick={onSuccess} className="px-4 py-2 rounded-lg gradient-primary text-primary-foreground text-sm">Concluir</button>
          </div>
        </div>
      </ModalShell>
    );
  }
  return (
    <ModalShell title="Adicionar membro" onClose={onClose}>
      <div className="space-y-4">
        <Field label="E-mail *"><input type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} className={INPUT_CLS} placeholder="funcionario@empresa.com.br" /></Field>
        <Field label="Papel">
          <select value={form.role} onChange={e => setForm({ ...form, role: e.target.value as "admin" | "member" })} className={INPUT_CLS}>
            <option value="member">Membro — processa PDFs, sem acesso financeiro</option>
            <option value="admin">Admin — vê cobrança e gerencia membros</option>
          </select>
        </Field>
        {form.role === "admin" && (
          <label className="flex items-center gap-2 text-sm text-foreground">
            <input type="checkbox" checked={form.can_process} onChange={e => setForm({ ...form, can_process: e.target.checked })} className="rounded" />
            Admin também pode processar PDFs
          </label>
        )}
        <div className="text-xs text-muted-foreground">
          Se o e-mail já for usuário avulso, migramos a conta. Se não existir, criamos e geramos um link de convite.
        </div>
        <div className="flex justify-end gap-2 pt-3 border-t border-border/30">
          <button onClick={onClose} disabled={busy} className="px-4 py-2 rounded-lg border border-border/50 text-muted-foreground hover:text-foreground text-sm">Cancelar</button>
          <button onClick={submit} disabled={busy} className="px-4 py-2 rounded-lg gradient-primary text-primary-foreground text-sm font-medium disabled:opacity-50">{busy ? "Adicionando…" : "Adicionar"}</button>
        </div>
      </div>
    </ModalShell>
  );
}

// ═══════════════════════════════════════════════════════════════════
// CONFIRM DIALOG
// ═══════════════════════════════════════════════════════════════════
function ConfirmDialog({ title, message, confirmLabel, danger, loading, onConfirm, onCancel }: {
  title: string; message: string; confirmLabel: string; danger?: boolean; loading?: boolean;
  onConfirm: () => void; onCancel: () => void;
}) {
  return (
    <ModalShell title={title} onClose={onCancel}>
      <p className="text-sm text-muted-foreground mb-5">{message}</p>
      <div className="flex justify-end gap-2">
        <button onClick={onCancel} disabled={loading} className="px-4 py-2 rounded-lg border border-border/50 text-muted-foreground hover:text-foreground text-sm">Cancelar</button>
        <button onClick={onConfirm} disabled={loading}
                className={`px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 ${
                  danger ? "bg-destructive text-destructive-foreground hover:bg-destructive/90" : "gradient-primary text-primary-foreground"
                }`}>
          {loading ? "Aguarde…" : confirmLabel}
        </button>
      </div>
    </ModalShell>
  );
}
