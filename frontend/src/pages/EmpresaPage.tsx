// frontend/src/pages/EmpresaPage.tsx
import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Building, Users, CreditCard, Settings, ArrowRight, AlertCircle,
  ShoppingCart, ExternalLink, Crown, Pause, Play, Trash2, UserPlus,
  Copy, RefreshCw, X, Check, MoreVertical, LogOut, Receipt,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

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
}
interface Member {
  id: number; email: string; is_active: boolean;
  org_role: string | null; can_process: boolean; page_count: number;
}
interface OrgMeResponse {
  organization: Organization;
  member_count: number;
  estimated_invoice_cents: number;
  estimated_invoice_brl: number;
}
interface Invoice {
  id: string; number: string | null; status: string;
  amount_due_cents: number; amount_paid_cents: number; currency: string;
  created: number; period_start: number; period_end: number;
  hosted_invoice_url: string | null; invoice_pdf: string | null;
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
  let data: any = {}; try { data = await r.json(); } catch {}
  return { ok: r.ok, status: r.status, data };
}
const api = {
  getMe:          ()           => apiCall("/api/org/me"),
  updateMe:       (b: any)     => apiCall("/api/org/me", { method: "PATCH", body: JSON.stringify(b) }),
  listMembers:    ()           => apiCall("/api/org/members"),
  inviteMember:   (b: any)     => apiCall("/api/org/members", { method: "POST", body: JSON.stringify(b) }),
  updateMember:   (uid: number, b: any) => apiCall(`/api/org/members/${uid}`, { method: "PATCH", body: JSON.stringify(b) }),
  removeMember:   (uid: number) => apiCall(`/api/org/members/${uid}`, { method: "DELETE" }),
  createCheckout: ()           => apiCall("/api/org/checkout-session", { method: "POST" }),
  createPortal:   ()           => apiCall("/api/org/portal-session", { method: "POST" }),
  listInvoices:   ()           => apiCall("/api/org/invoices"),
};

// ═══════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════
const INPUT_CLS = "w-full bg-muted/30 border border-border/50 rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary transition-colors";

const formatBRL = (cents: number) =>
  `R$ ${(cents / 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const formatDate = (ts: number | string | null) => {
  if (!ts) return "—";
  const d = typeof ts === "number" ? new Date(ts * 1000) : new Date(ts);
  return d.toLocaleDateString("pt-BR");
};
const formatCNPJ = (raw: string | null) => {
  if (!raw) return "—";
  const d = raw.replace(/\D/g, "");
  if (d.length !== 14) return raw;
  return `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8,12)}-${d.slice(12)}`;
};
const orgInitials = (name: string) => {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
};
const statusInfo = (status: string) => {
  const map: Record<string, { label: string; cls: string; description: string }> = {
    awaiting_setup: { label: "AGUARDANDO CARTÃO", cls: "bg-amber-500/15 text-amber-300",
      description: "Cadastre um cartão para ativar o processamento de PDFs." },
    active:         { label: "ATIVA",              cls: "bg-emerald-500/15 text-emerald-300",
      description: "Tudo certo. Sua empresa está ativa." },
    past_due:       { label: "PAGAMENTO PENDENTE", cls: "bg-red-500/15 text-red-300",
      description: "A última fatura não foi paga. Regularize para continuar." },
    suspended:      { label: "SUSPENSA",           cls: "bg-slate-500/15 text-slate-300",
      description: "Empresa suspensa pelo administrador do sistema." },
    inactive:       { label: "INATIVA",            cls: "bg-slate-500/15 text-slate-400",
      description: "Empresa inativa." },
  };
  return map[status] || { label: status.toUpperCase(), cls: "bg-slate-500/15 text-slate-300", description: "" };
};

// ═══════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════════
type EmpresaTab = "overview" | "members" | "billing" | "settings";

export default function EmpresaPage() {
  const navigate = useNavigate();
  const { logout, user: authUser } = useAuth();
  const [tab, setTab] = useState<EmpresaTab>("overview");
  const [orgData, setOrgData] = useState<OrgMeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMe = useCallback(async () => {
    setLoading(true);
    try {
      const { ok, status, data } = await api.getMe();
      if (ok) { setOrgData(data); setError(null); }
      else if (status === 400) setError("Esta área é exclusiva de administradores de empresa.");
      else setError(data.msg || "Erro ao carregar empresa.");
    } catch { setError("Erro de rede."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchMe(); }, [fetchMe]);

  useEffect(() => {
    if (!loading && error?.includes("exclusiva")) {
      toast.error(error);
      navigate("/app", { replace: true });
    }
  }, [loading, error, navigate]);

  if (loading) {
    return (
      <div className="min-h-screen gradient-bg flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-[3px] border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-muted-foreground text-sm">Carregando empresa...</p>
        </div>
      </div>
    );
  }

  if (error || !orgData) {
    return (
      <div className="min-h-screen gradient-bg flex items-center justify-center px-4">
        <div className="max-w-md text-center">
          <AlertCircle className="w-12 h-12 mx-auto text-muted-foreground mb-3" />
          <h2 className="text-xl font-semibold text-foreground mb-2">Algo deu errado</h2>
          <p className="text-muted-foreground text-sm mb-4">{error}</p>
          <button onClick={() => navigate("/app")} className="px-4 py-2 rounded-lg gradient-primary text-primary-foreground text-sm">
            Voltar para o sistema
          </button>
        </div>
      </div>
    );
  }

  const { organization: org } = orgData;
  const status = statusInfo(org.plan_status);
  const canProcess = (authUser as any)?.can_process !== false;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b border-border/50 bg-card/80 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg gradient-primary text-primary-foreground flex items-center justify-center text-sm font-semibold">
              {orgInitials(org.name)}
            </div>
            <div>
              <h1 className="text-foreground font-semibold">{org.name}</h1>
              <div className="flex items-center gap-2 text-xs">
                <span className={`text-[10px] px-2 py-0.5 rounded-md ${status.cls}`}>{status.label}</span>
                <span className="text-muted-foreground">· {authUser?.email}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {canProcess && (
              <button onClick={() => navigate("/app")} className="flex items-center gap-2 px-4 py-2 rounded-lg border border-border/50 text-muted-foreground hover:text-foreground hover:border-border text-sm transition-all">
                Acessar sistema <ArrowRight className="w-4 h-4" />
              </button>
            )}
            <button onClick={() => { logout(); navigate("/login"); }} className="flex items-center gap-2 px-4 py-2 rounded-lg border border-destructive/30 text-destructive hover:bg-destructive/10 transition-all text-sm">
              <LogOut className="w-4 h-4" /> Sair
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
        <div className="flex gap-1 border-b border-border/50 mb-6 overflow-x-auto">
          <TabButton active={tab==="overview"} onClick={()=>setTab("overview")} icon={<Building className="w-4 h-4" />}>Visão geral</TabButton>
          <TabButton active={tab==="members"}  onClick={()=>setTab("members")}  icon={<Users className="w-4 h-4" />}>Funcionários</TabButton>
          <TabButton active={tab==="billing"}  onClick={()=>setTab("billing")}  icon={<CreditCard className="w-4 h-4" />}>Faturamento</TabButton>
          <TabButton active={tab==="settings"} onClick={()=>setTab("settings")} icon={<Settings className="w-4 h-4" />}>Configurações</TabButton>
        </div>

        {tab==="overview" && <OverviewTab orgData={orgData} onChange={fetchMe} />}
        {tab==="members"  && <MembersTab onChange={fetchMe} />}
        {tab==="billing"  && <BillingTab org={org} />}
        {tab==="settings" && <SettingsTab org={org} onSaved={fetchMe} />}
      </main>
    </div>
  );
}

function TabButton({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button onClick={onClick} className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-all whitespace-nowrap -mb-[1px] ${
      active ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
    }`}>
      {icon}{children}
    </button>
  );
}

// ═══════════════════════════════════════════════════════════════════
// OVERVIEW
// ═══════════════════════════════════════════════════════════════════
function OverviewTab({ orgData, onChange }: { orgData: OrgMeResponse; onChange: () => void }) {
  const { organization: org, member_count, estimated_invoice_cents } = orgData;
  const status = statusInfo(org.plan_status);
  const [busy, setBusy] = useState(false);

  const genCheckout = async () => {
    setBusy(true);
    try {
      const { ok, data } = await api.createCheckout();
      if (ok && data.url) window.location.href = data.url;
      else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setBusy(false); }
  };
  const genPortal = async () => {
    setBusy(true);
    try {
      const { ok, data } = await api.createPortal();
      if (ok && data.url) window.location.href = data.url;
      else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-5">
      {(org.plan_status === "awaiting_setup" || org.plan_status === "past_due" || org.plan_status === "suspended") && (
        <div className={`rounded-lg border px-4 py-3 flex items-start gap-3 ${
          org.plan_status === "past_due"
            ? "bg-red-500/10 border-red-500/30 text-red-200"
            : "bg-amber-500/10 border-amber-500/30 text-amber-200"
        }`}>
          <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="font-medium text-sm">{status.label}</div>
            <p className="text-sm mt-0.5 opacity-90">{status.description}</p>
            {org.plan_status === "awaiting_setup" && (
              <button onClick={genCheckout} disabled={busy} className="mt-3 px-4 py-2 rounded-md gradient-primary text-primary-foreground text-sm font-medium flex items-center gap-2 disabled:opacity-50">
                <ShoppingCart className="w-4 h-4" />{busy ? "Abrindo..." : "Cadastrar cartão"}
              </button>
            )}
            {org.plan_status === "past_due" && (
              <button onClick={genPortal} disabled={busy} className="mt-3 px-4 py-2 rounded-md gradient-primary text-primary-foreground text-sm font-medium flex items-center gap-2 disabled:opacity-50">
                <CreditCard className="w-4 h-4" />{busy ? "Abrindo..." : "Regularizar pagamento"}
              </button>
            )}
          </div>
        </div>
      )}

      {org.pending_price_per_page_cents && (
        <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 px-4 py-3 text-amber-200 text-sm flex items-start gap-3">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            O preço da sua empresa vai mudar para <span className="font-medium">{formatBRL(org.pending_price_per_page_cents)}</span> por página a partir do próximo ciclo
            (atual: <span className="font-medium">{formatBRL(org.price_per_page_cents)}</span>).
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Páginas no ciclo" value={org.page_count.toLocaleString("pt-BR")} hint={`${formatBRL(org.price_per_page_cents)} por pág.`} />
        <StatCard label="A faturar" value={formatBRL(estimated_invoice_cents)} hint={org.next_reset_date ? `Vence em ${formatDate(org.next_reset_date)}` : ""} />
        <StatCard label="Funcionários" value={member_count} hint="ativos" />
        <StatCard label="Status" value={status.label} hint={status.description} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-border/50 bg-card/30 p-5">
          <h3 className="text-foreground font-medium mb-3 flex items-center gap-2"><CreditCard className="w-4 h-4" /> Plano</h3>
          <dl className="space-y-2 text-sm">
            <Row k="Preço por página" v={formatBRL(org.price_per_page_cents)} />
            <Row k="Ciclo" v="Mensal · pós-pago" />
            <Row k="Próxima fatura" v={formatDate(org.next_reset_date)} />
            <Row k="Forma de pagamento" v={org.stripe_customer_id ? "Cartão cadastrado" : "Não cadastrado"} />
          </dl>
          {org.stripe_customer_id && (
            <button onClick={genPortal} disabled={busy} className="mt-4 w-full px-3 py-2 rounded-md border border-border/50 text-muted-foreground hover:text-foreground hover:border-border text-sm flex items-center justify-center gap-2 transition-all disabled:opacity-50">
              <ExternalLink className="w-4 h-4" />{busy ? "Abrindo..." : "Gerenciar cobrança"}
            </button>
          )}
        </div>

        <div className="rounded-xl border border-border/50 bg-card/30 p-5">
          <h3 className="text-foreground font-medium mb-3 flex items-center gap-2"><Building className="w-4 h-4" /> Dados</h3>
          <dl className="space-y-2 text-sm">
            <Row k="Nome fantasia" v={org.name} />
            {org.legal_name && <Row k="Razão social" v={org.legal_name} />}
            <Row k="CNPJ" v={formatCNPJ(org.cnpj)} mono />
            <Row k="E-mail de cobrança" v={org.billing_email} />
          </dl>
        </div>
      </div>
    </div>
  );
}
function Row({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className={`text-foreground ${mono ? "font-mono" : ""}`}>{v}</dd>
    </div>
  );
}
function StatCard({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-lg bg-card/30 border border-border/30 p-3">
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="text-foreground text-xl font-semibold mt-1">{value}</div>
      {hint && <div className="text-muted-foreground text-[11px] mt-1">{hint}</div>}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// MEMBERS
// ═══════════════════════════════════════════════════════════════════
function MembersTab({ onChange }: { onChange: () => void }) {
  const { user: authUser } = useAuth();
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);

  const fetch_ = useCallback(async () => {
    setLoading(true);
    try {
      const { ok, data } = await api.listMembers();
      if (ok) setMembers(data.members || []); else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { fetch_(); }, [fetch_]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-foreground font-semibold">Funcionários ({members.length})</h3>
          <p className="text-muted-foreground text-xs mt-1">Convide e gerencie quem processa PDFs.</p>
        </div>
        <button onClick={() => setShowInvite(true)} className="flex items-center gap-2 px-4 py-2 rounded-lg gradient-primary text-primary-foreground text-sm font-medium hover:shadow-lg transition-all">
          <UserPlus className="w-4 h-4" /> Convidar
        </button>
      </div>

      <div className="rounded-xl border border-border/50 bg-card/30 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-muted-foreground text-sm">Carregando...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/30 text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="text-left  px-4 py-3 font-medium">Funcionário</th>
                  <th className="text-left  px-4 py-3 font-medium">Papel</th>
                  <th className="text-right px-4 py-3 font-medium">Páginas</th>
                  <th className="text-center px-4 py-3 font-medium">Ativo</th>
                  <th className="w-12"></th>
                </tr>
              </thead>
              <tbody>
                {members.map(m => (
                  <MemberRow key={m.id} member={m} currentEmail={authUser?.email} onChange={() => { fetch_(); onChange(); }} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showInvite && (
        <InviteMemberModal onClose={() => setShowInvite(false)} onSuccess={() => { setShowInvite(false); fetch_(); onChange(); }} />
      )}
    </div>
  );
}

function MemberRow({ member, currentEmail, onChange }: { member: Member; currentEmail?: string; onChange: () => void }) {
  const [menu, setMenu] = useState(false);
  const [busy, setBusy] = useState(false);
  const isAdmin = member.org_role === "admin";
  const isSelf = member.email === currentEmail;

  const update = async (b: any) => {
    setBusy(true);
    try {
      const { ok, data } = await api.updateMember(member.id, b);
      if (ok) { toast.success(data.msg || "Atualizado."); onChange(); }
      else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setBusy(false); setMenu(false); }
  };
  const remove = async () => {
    if (!confirm(`Remover ${member.email} da empresa?`)) return;
    setBusy(true);
    try {
      const { ok, data } = await api.removeMember(member.id);
      if (ok) { toast.success("Removido."); onChange(); } else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setBusy(false); setMenu(false); }
  };

  return (
    <tr className="border-t border-border/30 relative">
      <td className="px-4 py-3">
        <div className="text-foreground">{member.email}{isSelf && <span className="ml-2 text-xs text-primary">· você</span>}</div>
      </td>
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
        {member.is_active ? <Check className="w-4 h-4 text-emerald-400 mx-auto" /> : <X className="w-4 h-4 text-muted-foreground/50 mx-auto" />}
      </td>
      <td className="px-2 py-3 text-right">
        <button onClick={() => setMenu(o => !o)} className="p-1 rounded hover:bg-muted/30 text-muted-foreground">
          <MoreVertical className="w-4 h-4" />
        </button>
        {menu && (
          <>
            <div className="fixed inset-0 z-30" onClick={() => setMenu(false)} />
            <div className="absolute right-4 mt-1 w-56 rounded-lg border border-border/50 bg-card shadow-xl z-40 py-1 text-left text-sm">
              {isSelf ? (
                <div className="px-3 py-2 text-xs text-muted-foreground">Você não pode editar sua própria conta. Peça para outro admin.</div>
              ) : (
                <>
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
                    {member.is_active ? <><Pause className="w-4 h-4 text-amber-400" /> Desativar</> : <><Play className="w-4 h-4 text-emerald-400" /> Ativar</>}
                  </button>
                  <div className="border-t border-border/30 my-1" />
                  <button onClick={remove} disabled={busy} className="w-full px-3 py-2 hover:bg-destructive/10 flex items-center gap-2 text-destructive">
                    <Trash2 className="w-4 h-4" /> Remover da empresa
                  </button>
                </>
              )}
            </div>
          </>
        )}
      </td>
    </tr>
  );
}

function InviteMemberModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [form, setForm] = useState({ email: "", role: "member" as "admin" | "member", can_process: true });
  const [busy, setBusy] = useState(false);
  const [invite, setInvite] = useState<string | null>(null);

  const submit = async () => {
    if (!form.email) { toast.error("Informe o e-mail."); return; }
    setBusy(true);
    try {
      const { ok, data } = await api.inviteMember(form);
      if (ok) {
        if (data.invite_link) setInvite(data.invite_link);
        else { toast.success(`Funcionário ${data.was_migrated ? "migrado" : "adicionado"}.`); onSuccess(); }
      } else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setBusy(false); }
  };

  if (invite) {
    return (
      <ModalShell title="Funcionário convidado — envie o link" onClose={onSuccess}>
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">O funcionário precisa abrir este link para definir a senha.</p>
          <div className="rounded-lg bg-muted/30 border border-border/50 p-3 flex items-center gap-2">
            <code className="text-xs text-foreground font-mono truncate flex-1">{invite}</code>
            <button onClick={() => { navigator.clipboard.writeText(invite); toast.success("Copiado!"); }} className="text-xs px-2 py-1 rounded border border-border/50 hover:border-border text-foreground">
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
    <ModalShell title="Convidar funcionário" onClose={onClose}>
      <div className="space-y-4">
        <Field label="E-mail *">
          <input type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} className={INPUT_CLS} placeholder="funcionario@empresa.com.br" />
        </Field>
        <Field label="Papel">
          <select value={form.role} onChange={e => setForm({ ...form, role: e.target.value as any })} className={INPUT_CLS}>
            <option value="member">Membro — só processa PDFs</option>
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
          Geramos um link de convite. Envie manualmente (e-mail/WhatsApp) para a pessoa.
        </div>
        <div className="flex justify-end gap-2 pt-3 border-t border-border/30">
          <button onClick={onClose} disabled={busy} className="px-4 py-2 rounded-lg border border-border/50 text-muted-foreground hover:text-foreground text-sm">Cancelar</button>
          <button onClick={submit} disabled={busy} className="px-4 py-2 rounded-lg gradient-primary text-primary-foreground text-sm font-medium disabled:opacity-50">
            {busy ? "Convidando..." : "Convidar"}
          </button>
        </div>
      </div>
    </ModalShell>
  );
}

// ═══════════════════════════════════════════════════════════════════
// BILLING
// ═══════════════════════════════════════════════════════════════════
function BillingTab({ org }: { org: Organization }) {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const fetch_ = useCallback(async () => {
    setLoading(true);
    try {
      const { ok, data } = await api.listInvoices();
      if (ok) setInvoices(data.invoices || []); else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { fetch_(); }, [fetch_]);

  const genPortal = async () => {
    setBusy(true);
    try {
      const { ok, data } = await api.createPortal();
      if (ok && data.url) window.location.href = data.url; else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setBusy(false); }
  };
  const genCheckout = async () => {
    setBusy(true);
    try {
      const { ok, data } = await api.createCheckout();
      if (ok && data.url) window.location.href = data.url; else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-border/50 bg-card/30 p-5">
        <h3 className="text-foreground font-medium mb-2 flex items-center gap-2"><CreditCard className="w-4 h-4" /> Forma de pagamento</h3>
        {org.stripe_customer_id ? (
          <>
            <p className="text-muted-foreground text-sm mb-4">
              Use o portal do Stripe para trocar o cartão, baixar faturas e atualizar dados de cobrança.
            </p>
            <button onClick={genPortal} disabled={busy} className="px-4 py-2 rounded-lg gradient-primary text-primary-foreground text-sm font-medium flex items-center gap-2 disabled:opacity-50">
              <ExternalLink className="w-4 h-4" />{busy ? "Abrindo..." : "Abrir portal do Stripe"}
            </button>
          </>
        ) : (
          <>
            <p className="text-muted-foreground text-sm mb-4">
              Sua empresa ainda não tem cartão. Sem isso ninguém da empresa consegue processar PDFs.
            </p>
            <button onClick={genCheckout} disabled={busy} className="px-4 py-2 rounded-lg gradient-primary text-primary-foreground text-sm font-medium flex items-center gap-2 disabled:opacity-50">
              <ShoppingCart className="w-4 h-4" />{busy ? "Abrindo..." : "Cadastrar cartão"}
            </button>
          </>
        )}
      </div>

      <div className="rounded-xl border border-border/50 bg-card/30 overflow-hidden">
        <div className="px-5 py-4 border-b border-border/30">
          <h3 className="text-foreground font-medium flex items-center gap-2"><Receipt className="w-4 h-4" /> Histórico de faturas</h3>
        </div>
        {loading ? (
          <div className="p-8 text-center text-muted-foreground text-sm">Carregando...</div>
        ) : invoices.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground text-sm">
            Nenhuma fatura ainda. Elas aparecem aqui depois do primeiro fechamento de ciclo.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/20 text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="text-left  px-4 py-3 font-medium">Número</th>
                  <th className="text-left  px-4 py-3 font-medium">Período</th>
                  <th className="text-right px-4 py-3 font-medium">Valor</th>
                  <th className="text-center px-4 py-3 font-medium">Status</th>
                  <th className="w-32"></th>
                </tr>
              </thead>
              <tbody>
                {invoices.map(inv => (
                  <tr key={inv.id} className="border-t border-border/30">
                    <td className="px-4 py-3 text-foreground font-mono text-xs">{inv.number || inv.id.slice(0, 12)}</td>
                    <td className="px-4 py-3 text-muted-foreground text-xs">{formatDate(inv.period_start)} → {formatDate(inv.period_end)}</td>
                    <td className="px-4 py-3 text-right text-foreground">{formatBRL(inv.amount_paid_cents || inv.amount_due_cents)}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`text-[10px] px-2 py-0.5 rounded-md ${
                        inv.status === "paid" ? "bg-emerald-500/15 text-emerald-300"
                        : inv.status === "open" ? "bg-amber-500/15 text-amber-300"
                        : "bg-slate-500/15 text-slate-300"
                      }`}>
                        {inv.status?.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {inv.hosted_invoice_url && (
                        <a href={inv.hosted_invoice_url} target="_blank" rel="noopener noreferrer" className="text-xs px-2 py-1 rounded border border-border/50 hover:border-border text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
                          <ExternalLink className="w-3 h-3" /> Ver
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// SETTINGS
// ═══════════════════════════════════════════════════════════════════
function SettingsTab({ org, onSaved }: { org: Organization; onSaved: () => void }) {
  const [form, setForm] = useState({ name: org.name, billing_email: org.billing_email });
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const { ok, data } = await api.updateMe(form);
      if (ok) { toast.success("Dados atualizados."); onSaved(); }
      else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-border/50 bg-card/30 p-5">
        <h3 className="text-foreground font-medium mb-4">Dados editáveis</h3>
        <div className="space-y-4">
          <Field label="Nome fantasia">
            <input type="text" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className={INPUT_CLS} />
          </Field>
          <Field label="E-mail de cobrança">
            <input type="email" value={form.billing_email} onChange={e => setForm({ ...form, billing_email: e.target.value })} className={INPUT_CLS} />
          </Field>
          <button onClick={submit} disabled={busy} className="px-4 py-2 rounded-lg gradient-primary text-primary-foreground text-sm font-medium disabled:opacity-50">
            {busy ? "Salvando..." : "Salvar alterações"}
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-border/50 bg-card/30 p-5">
        <h3 className="text-foreground font-medium mb-4">Informações administrativas</h3>
        <p className="text-muted-foreground text-xs mb-4">
          Esses campos são gerenciados pela equipe Sistema Ponto. Para alterar, entre em contato com o suporte.
        </p>
        <dl className="space-y-2 text-sm">
          <Row k="CNPJ" v={formatCNPJ(org.cnpj)} mono />
          <Row k="Razão social" v={org.legal_name || "—"} />
          <Row k="Preço por página" v={formatBRL(org.price_per_page_cents)} />
          {org.pending_price_per_page_cents && (
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Novo preço (próx. ciclo)</dt>
              <dd className="text-amber-400 font-medium">{formatBRL(org.pending_price_per_page_cents)}</dd>
            </div>
          )}
        </dl>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// SHARED
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
