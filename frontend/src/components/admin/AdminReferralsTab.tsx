// frontend/src/components/admin/AdminReferralsTab.tsx
//
// Aba de indicações no painel admin. Duas sub-views:
//   - Histórico completo (todas as indicações individuais)
//   - Por indicador (agregado — quem indicou quantos)

import { useState, useEffect, useCallback } from "react";
import {
  Users, Search, Loader2, TrendingUp,
  CheckCircle2, Clock, ChevronLeft, ChevronRight,
} from "lucide-react";
import { toast } from "sonner";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function getToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("jwt_token");
}

async function adminFetch(url: string, options: RequestInit = {}) {
  const token = getToken();
  const res = await fetch(`${API_BASE_URL}${url}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    },
  });
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Sessão expirada.");
  }
  return res;
}

interface ReferralItem {
  id: number;
  referrer_id: number;
  referrer_email: string;
  referrer_code: string;
  referred_id: number;
  referred_email: string;
  referred_plan_status: string | null;
  status: "pending" | "converted" | "expired";
  plan_at_conversion: string | null;
  discount_granted_pct: number;
  created_at: string | null;
  converted_at: string | null;
}

interface ReferrerItem {
  user_id: number;
  email: string;
  referral_code: string;
  plan_status: string;
  converted_count: number;
  pending_count: number;
  total_count: number;
  discount_credits: number;
  active_discount_pct: number;
  next_month_discount_pct: number;
}

interface SummaryStats {
  total: number;
  converted: number;
  pending: number;
  conversion_rate_pct: number;
  total_pct_distributed: number;
}

const AdminReferralsTab = () => {
  const [view, setView] = useState<"all" | "by_referrer">("all");

  const [referrals, setReferrals] = useState<ReferralItem[]>([]);
  const [refStats, setRefStats] = useState<SummaryStats | null>(null);
  const [refPage, setRefPage] = useState(1);
  const [refPages, setRefPages] = useState(1);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(false);

  const [referrers, setReferrers] = useState<ReferrerItem[]>([]);
  const [refersPage, setRefersPage] = useState(1);
  const [refersPages, setRefersPages] = useState(1);
  const [loadingReferrers, setLoadingReferrers] = useState(false);

  const fetchReferrals = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(refPage),
        per_page: "20",
      });
      if (search) params.set("search", search);
      if (statusFilter !== "all") params.set("status", statusFilter);

      const res = await adminFetch(`/api/admin/referrals?${params}`);
      const data = await res.json();
      if (res.ok) {
        setReferrals(data.items || []);
        setRefPages(data.pages || 1);
        const rawStats = data.stats || {};
        setRefStats({
          total: rawStats.total ?? 0,
          converted: rawStats.converted ?? 0,
          pending: rawStats.pending ?? 0,
          total_pct_distributed: rawStats.total_discount_pct_distributed ?? 0,
          conversion_rate_pct:
            rawStats.total > 0
              ? Math.round((rawStats.converted / rawStats.total) * 100 * 10) / 10
              : 0,
        });
      } else {
        toast.error(data.msg || "Erro ao carregar indicações.");
      }
    } catch {
      toast.error("Erro de rede.");
    } finally {
      setLoading(false);
    }
  }, [refPage, search, statusFilter]);

  const fetchReferrers = useCallback(async () => {
    setLoadingReferrers(true);
    try {
      const params = new URLSearchParams({
        page: String(refersPage),
        per_page: "20",
      });
      const res = await adminFetch(`/api/admin/referrers?${params}`);
      const data = await res.json();
      if (res.ok) {
        setReferrers(data.items || []);
        setRefersPages(data.pages || 1);
      } else {
        toast.error(data.msg || "Erro.");
      }
    } catch {
      toast.error("Erro de rede.");
    } finally {
      setLoadingReferrers(false);
    }
  }, [refersPage]);

  useEffect(() => {
    if (view === "all") fetchReferrals();
    else fetchReferrers();
  }, [view, fetchReferrals, fetchReferrers]);

  const formatDate = (iso: string | null) => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleDateString("pt-BR", {
        day: "2-digit",
        month: "short",
        year: "2-digit",
      });
    } catch {
      return "—";
    }
  };

  const planLabel: Record<string, string> = {
    basic: "Básico",
    standard: "Padrão",
    premium: "Premium",
    free: "Free",
    past_due: "Pend.",
  };

  return (
    <div>
      {refStats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <StatCard
            label="Indicações totais"
            value={String(refStats.total)}
            icon={<Users className="w-4 h-4 text-muted-foreground" />}
          />
          <StatCard
            label="Convertidas"
            value={String(refStats.converted)}
            highlight="text-emerald-600 dark:text-emerald-400"
            icon={<CheckCircle2 className="w-4 h-4 text-emerald-500" />}
          />
          <StatCard
            label="Taxa de conversão"
            value={`${refStats.conversion_rate_pct}%`}
            icon={<TrendingUp className="w-4 h-4 text-primary" />}
          />
          <StatCard
            label="Desconto distribuído"
            value={`${refStats.total_pct_distributed}%`}
            icon={<TrendingUp className="w-4 h-4 text-amber-500" />}
          />
        </div>
      )}

      <div className="flex items-center gap-1 mb-4 border-b border-border/50">
        <SubTabBtn active={view === "all"} onClick={() => setView("all")}>
          Histórico completo
        </SubTabBtn>
        <SubTabBtn active={view === "by_referrer"} onClick={() => setView("by_referrer")}>
          Por indicador
        </SubTabBtn>
      </div>

      {view === "all" && (
        <>
          <div className="flex flex-wrap gap-3 mb-4">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setSearch(searchInput);
                setRefPage(1);
              }}
              className="flex-1 flex items-center gap-2 min-w-[250px]"
            >
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <input
                  type="text"
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  placeholder="Buscar por e-mail..."
                  className="w-full pl-9 pr-3 py-2 text-sm rounded-md bg-background border border-border/50 focus:border-primary outline-none"
                />
              </div>
              <button
                type="submit"
                className="px-4 py-2 text-sm font-medium rounded-md bg-foreground text-background hover:opacity-90"
              >
                Buscar
              </button>
            </form>

            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setRefPage(1);
              }}
              className="px-3 py-2 text-sm rounded-md bg-background border border-border/50 focus:border-primary outline-none"
            >
              <option value="all">Todos os status</option>
              <option value="converted">Convertidas</option>
              <option value="pending">Aguardando</option>
            </select>
          </div>

          <div className="glass-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border/50 bg-muted/20">
                    <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground uppercase">Indicado</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground uppercase">Indicado por</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground uppercase">Cadastro</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground uppercase">Status</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground uppercase">Plano</th>
                    <th className="text-right px-4 py-3 text-xs font-medium text-muted-foreground uppercase">Desconto</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan={6} className="p-8 text-center"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground mx-auto" /></td></tr>
                  ) : referrals.length === 0 ? (
                    <tr><td colSpan={6} className="p-8 text-center text-muted-foreground">Nenhuma indicação encontrada.</td></tr>
                  ) : (
                    referrals.map((r) => (
                      <tr key={r.id} className="border-b border-border/30 last:border-0 hover:bg-muted/20">
                        <td className="px-4 py-3 text-foreground"><div className="font-medium text-xs">{r.referred_email}</div></td>
                        <td className="px-4 py-3 text-muted-foreground">
                          <div className="text-xs">{r.referrer_email}</div>
                          <div className="text-[10px] font-mono text-muted-foreground/70">{r.referrer_code}</div>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground text-xs">{formatDate(r.created_at)}</td>
                        <td className="px-4 py-3"><StatusPill status={r.status} /></td>
                        <td className="px-4 py-3 text-muted-foreground text-xs">{r.plan_at_conversion ? planLabel[r.plan_at_conversion] ?? r.plan_at_conversion : "—"}</td>
                        <td className="px-4 py-3 text-right">
                          {r.status === "converted" ? (
                            <span className="text-emerald-600 dark:text-emerald-400 font-semibold">+{r.discount_granted_pct}%</span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {refPages > 1 && (
            <Pagination page={refPage} totalPages={refPages} onChange={setRefPage} />
          )}
        </>
      )}

      {view === "by_referrer" && (
        <>
          <div className="glass-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border/50 bg-muted/20">
                    <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground uppercase">Usuário</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground uppercase">Código</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-muted-foreground uppercase">Plano</th>
                    <th className="text-right px-4 py-3 text-xs font-medium text-muted-foreground uppercase">Convertidos</th>
                    <th className="text-right px-4 py-3 text-xs font-medium text-muted-foreground uppercase">Pendentes</th>
                    <th className="text-right px-4 py-3 text-xs font-medium text-muted-foreground uppercase">Desc. ativo</th>
                    <th className="text-right px-4 py-3 text-xs font-medium text-muted-foreground uppercase">Próximo mês</th>
                  </tr>
                </thead>
                <tbody>
                  {loadingReferrers ? (
                    <tr><td colSpan={7} className="p-8 text-center"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground mx-auto" /></td></tr>
                  ) : referrers.length === 0 ? (
                    <tr><td colSpan={7} className="p-8 text-center text-muted-foreground">Nenhum usuário com indicações ainda.</td></tr>
                  ) : (
                    referrers.map((r) => (
                      <tr key={r.user_id} className="border-b border-border/30 last:border-0 hover:bg-muted/20">
                        <td className="px-4 py-3 text-foreground text-xs">{r.email}</td>
                        <td className="px-4 py-3 font-mono text-[11px] text-muted-foreground">{r.referral_code}</td>
                        <td className="px-4 py-3 text-muted-foreground text-xs">{planLabel[r.plan_status] ?? r.plan_status}</td>
                        <td className="px-4 py-3 text-right font-semibold text-foreground">{r.converted_count}</td>
                        <td className="px-4 py-3 text-right text-muted-foreground">{r.pending_count}</td>
                        <td className="px-4 py-3 text-right">
                          {r.active_discount_pct > 0 ? (
                            <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                              {r.active_discount_pct}%
                              {r.active_discount_pct >= 40 && <span className="text-[10px] ml-1 opacity-60">(máx)</span>}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">
                          {r.next_month_discount_pct > 0 ? (
                            <span className="text-primary font-semibold">+{r.next_month_discount_pct}%</span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {refersPages > 1 && (
            <Pagination page={refersPage} totalPages={refersPages} onChange={setRefersPage} />
          )}
        </>
      )}
    </div>
  );
};

function StatCard({ label, value, icon, highlight }: { label: string; value: string; icon?: React.ReactNode; highlight?: string }) {
  return (
    <div className="bg-muted/30 rounded-lg p-4">
      <div className="flex items-center gap-1.5 mb-1">
        {icon}
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
      <div className={`text-xl font-bold ${highlight ?? "text-foreground"}`}>{value}</div>
    </div>
  );
}

function SubTabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium border-b-2 transition ${active ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}
    >
      {children}
    </button>
  );
}

function StatusPill({ status }: { status: string }) {
  const cfg: Record<string, { cls: string; label: string; icon: React.ReactNode }> = {
    converted: { cls: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400", label: "Convertido", icon: <CheckCircle2 className="w-3 h-3" /> },
    pending: { cls: "bg-amber-500/15 text-amber-600 dark:text-amber-400", label: "Aguardando", icon: <Clock className="w-3 h-3" /> },
    expired: { cls: "bg-muted text-muted-foreground", label: "Expirado", icon: null },
  };
  const c = cfg[status] ?? cfg.expired;
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded ${c.cls}`}>
      {c.icon}
      {c.label}
    </span>
  );
}

function Pagination({ page, totalPages, onChange }: { page: number; totalPages: number; onChange: (p: number) => void }) {
  return (
    <div className="flex items-center justify-between mt-4 text-sm">
      <button
        onClick={() => onChange(page - 1)}
        disabled={page <= 1}
        className="flex items-center gap-1 px-3 py-1.5 rounded-md border border-border/50 hover:bg-muted/50 disabled:opacity-40"
      >
        <ChevronLeft className="w-4 h-4" />
        Anterior
      </button>
      <span className="text-muted-foreground">Página {page} de {totalPages}</span>
      <button
        onClick={() => onChange(page + 1)}
        disabled={page >= totalPages}
        className="flex items-center gap-1 px-3 py-1.5 rounded-md border border-border/50 hover:bg-muted/50 disabled:opacity-40"
      >
        Próxima
        <ChevronRight className="w-4 h-4" />
      </button>
    </div>
  );
}

export default AdminReferralsTab;
