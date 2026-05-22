// frontend/src/pages/AdminPage.tsx
//
// Painel Admin com sistema de abas:
//   - Usuários (tela original completa, preservada)
//   - Indicações (nova)
//   - Promoções (nova)

import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Users, Search, Filter, RefreshCw, Trash2, KeyRound,
  Edit3, ChevronUp, ChevronDown, ChevronsUpDown, ChevronLeft,
  ChevronRight, Shield, LogOut, LayoutDashboard, X, Check,
  AlertTriangle, RotateCcw, UserCheck, UserX, Loader2,
  Gift, UserPlus, Megaphone, Wrench, Building,
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import AdminReferralsTab from "@/components/admin/AdminReferralsTab";
import AdminPromotionsTab from "@/components/admin/AdminPromotionsTab";
import AdminAnnouncementsTab from "@/components/admin/AdminAnnouncementsTab";
import AdminMaintenanceTab from "@/components/admin/AdminMaintenanceTab";
import AdminOrganizationsTab from "@/components/admin/AdminOrganizationsTab";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

interface AdminUser {
  id: number;
  email: string;
  name?: string;
  is_active: boolean;
  role: string;
  plan_status: string;
  page_count: number;
  stripe_customer_id?: string | null;
}

interface UsersResponse {
  users: AdminUser[];
  total: number;
  pages: number;
  current_page: number;
}

function getToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("jwt_token");
}

async function adminFetch(url: string, options: RequestInit = {}) {
  const token = getToken();
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    ...(options.headers as Record<string, string>),
  };
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`${API_BASE_URL}${url}`, { ...options, headers });
  if (res.status === 401) {
    localStorage.removeItem("access_token");
    localStorage.removeItem("jwt_token");
    window.location.href = "/login";
    throw new Error("Sessão expirada.");
  }
  return res;
}

const PLAN_LABELS: Record<string, string> = {
  free: "Free Trial",
  basic: "Básico",
  standard: "Padrão",
  premium: "Premium",
  past_due: "Pend. Pagamento",
  inactive: "Inativo",
};

const PLAN_COLORS: Record<string, string> = {
  free: "text-muted-foreground bg-muted/50 border-border/50",
  basic: "text-blue-400 bg-blue-400/10 border-blue-400/20",
  standard: "text-primary bg-primary/10 border-primary/20",
  premium: "text-amber-400 bg-amber-400/10 border-amber-400/20",
  past_due: "text-destructive bg-destructive/10 border-destructive/20",
  inactive: "text-muted-foreground bg-muted/30 border-border/30",
};

/* ═══════════════════ Modal Overlay ═══════════════════ */
function ModalOverlay({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 10 }}
          className="w-full max-w-md"
          onClick={(e) => e.stopPropagation()}
        >
          {children}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

/* ═══════════════════ Edit User Modal ═══════════════════ */
function EditUserModal({ user, onClose, onSuccess }: { user: AdminUser; onClose: () => void; onSuccess: () => void }) {
  const [email, setEmail] = useState(user.email);
  const [role, setRole] = useState(user.role);
  const [planStatus, setPlanStatus] = useState(user.plan_status);
  const [pageCount, setPageCount] = useState(String(user.page_count));
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const count = parseInt(pageCount, 10);
    if (isNaN(count) || count < 0) { toast.error("Contagem de páginas inválida."); return; }
    setLoading(true);
    try {
      const res = await adminFetch(`/api/admin/users/${user.id}`, {
        method: "PUT",
        body: JSON.stringify({ email, role, plan_status: planStatus, page_count: count }),
      });
      const data = await res.json();
      if (res.ok) { toast.success(data.msg || "Usuário atualizado!"); onSuccess(); onClose(); }
      else toast.error(data.msg || "Erro ao salvar.");
    } catch { toast.error("Erro de rede."); }
    finally { setLoading(false); }
  };

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-card border border-border rounded-2xl overflow-hidden shadow-xl">
        <div className="flex items-center justify-between p-5 border-b border-border/50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
              <Edit3 className="w-4 h-4 text-primary" />
            </div>
            <h3 className="text-foreground font-semibold">Editar Usuário</h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all">
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="text-sm font-medium text-foreground mb-1.5 block">E-mail</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required disabled={loading}
              className="w-full px-3 py-2.5 rounded-lg bg-background/50 border border-border/50 text-foreground text-sm focus:outline-none focus:border-primary/60 focus:ring-1 focus:ring-primary/20 transition-all" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm font-medium text-foreground mb-1.5 block">Role</label>
              <select value={role} onChange={(e) => setRole(e.target.value)} disabled={loading}
                className="w-full px-3 py-2.5 rounded-lg bg-background/50 border border-border/50 text-foreground text-sm focus:outline-none focus:border-primary/60 transition-all">
                <option value="user">User</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <div>
              <label className="text-sm font-medium text-foreground mb-1.5 block">Plano</label>
              <select value={planStatus} onChange={(e) => setPlanStatus(e.target.value)} disabled={loading}
                className="w-full px-3 py-2.5 rounded-lg bg-background/50 border border-border/50 text-foreground text-sm focus:outline-none focus:border-primary/60 transition-all">
                <option value="free">Free Trial</option>
                <option value="basic">Básico</option>
                <option value="standard">Padrão</option>
                <option value="premium">Premium</option>
                <option value="past_due">Pend. Pagamento</option>
                <option value="inactive">Inativo</option>
              </select>
            </div>
          </div>
          <div>
            <label className="text-sm font-medium text-foreground mb-1.5 block">Páginas usadas</label>
            <input type="number" value={pageCount} onChange={(e) => setPageCount(e.target.value)} disabled={loading}
              className="w-full px-3 py-2.5 rounded-lg bg-background/50 border border-border/50 text-foreground text-sm focus:outline-none focus:border-primary/60 focus:ring-1 focus:ring-primary/20 transition-all" />
          </div>
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 px-4 py-2.5 rounded-lg border border-border/50 text-muted-foreground hover:text-foreground hover:border-border transition-all text-sm font-medium">Cancelar</button>
            <button type="submit" disabled={loading} className="flex-1 px-4 py-2.5 rounded-lg gradient-primary text-primary-foreground text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-50">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />} Salvar
            </button>
          </div>
        </form>
      </div>
    </ModalOverlay>
  );
}

/* ═══════════════════ Reset Password Modal ═══════════════════ */
function ResetPasswordModal({ user, onClose, onSuccess }: { user: AdminUser; onClose: () => void; onSuccess: () => void }) {
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword.length < 6) { toast.error("Senha deve ter pelo menos 6 caracteres."); return; }
    if (newPassword !== confirm) { toast.error("As senhas não coincidem."); return; }
    setLoading(true);
    try {
      const res = await adminFetch(`/api/admin/users/${user.id}`, {
        method: "PUT",
        body: JSON.stringify({ new_password: newPassword }),
      });
      const data = await res.json();
      if (res.ok) { toast.success(`Senha de ${user.email} resetada!`); onSuccess(); onClose(); }
      else toast.error(data.msg || "Erro ao resetar.");
    } catch { toast.error("Erro de rede."); }
    finally { setLoading(false); }
  };

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-card border border-border rounded-2xl overflow-hidden shadow-xl">
        <div className="flex items-center justify-between p-5 border-b border-border/50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
              <KeyRound className="w-4 h-4 text-amber-500" />
            </div>
            <div>
              <h3 className="text-foreground font-semibold">Resetar Senha</h3>
              <p className="text-muted-foreground text-xs">{user.email}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all">
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="text-sm font-medium text-foreground mb-1.5 block">Nova Senha</label>
            <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="Mín. 6 caracteres" required disabled={loading}
              className="w-full px-3 py-2.5 rounded-lg bg-background/50 border border-border/50 text-foreground text-sm focus:outline-none focus:border-amber-500/60 focus:ring-1 focus:ring-amber-500/20 transition-all" />
          </div>
          <div>
            <label className="text-sm font-medium text-foreground mb-1.5 block">Confirmar Senha</label>
            <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="Repita a senha" required disabled={loading}
              className="w-full px-3 py-2.5 rounded-lg bg-background/50 border border-border/50 text-foreground text-sm focus:outline-none focus:border-amber-500/60 focus:ring-1 focus:ring-amber-500/20 transition-all" />
          </div>
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 px-4 py-2.5 rounded-lg border border-border/50 text-muted-foreground hover:text-foreground hover:border-border transition-all text-sm font-medium">Cancelar</button>
            <button type="submit" disabled={loading} className="flex-1 px-4 py-2.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-50 transition-all">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />} Confirmar
            </button>
          </div>
        </form>
      </div>
    </ModalOverlay>
  );
}

/* ═══════════════════ Confirm Modal ═══════════════════ */
function ConfirmModal({ title, message, confirmLabel, onClose, onConfirm, loading, danger = true }: {
  title: string; message: string; confirmLabel: string; onClose: () => void; onConfirm: () => void; loading?: boolean; danger?: boolean;
}) {
  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-card border border-border rounded-2xl overflow-hidden shadow-xl p-6">
        <div className="flex items-start gap-4 mb-5">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${danger ? "bg-destructive/10 border border-destructive/20" : "bg-primary/10 border border-primary/20"}`}>
            <AlertTriangle className={`w-5 h-5 ${danger ? "text-destructive" : "text-primary"}`} />
          </div>
          <div>
            <h3 className="text-foreground font-semibold">{title}</h3>
            <p className="text-muted-foreground text-sm mt-1">{message}</p>
          </div>
        </div>
        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 px-4 py-2.5 rounded-lg border border-border/50 text-muted-foreground hover:text-foreground hover:border-border transition-all text-sm font-medium">Cancelar</button>
          <button onClick={onConfirm} disabled={loading}
            className={`flex-1 px-4 py-2.5 rounded-lg text-white text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-50 transition-all ${danger ? "bg-destructive hover:bg-destructive/80" : "gradient-primary"}`}>
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null} {confirmLabel}
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
}

/* ═══════════════════ Sort Icon ═══════════════════ */
function SortIcon({ field, sortField, sortOrder }: { field: string; sortField: string; sortOrder: string }) {
  if (field !== sortField) return <ChevronsUpDown className="w-3.5 h-3.5 text-muted-foreground/50" />;
  return sortOrder === "asc" ? <ChevronUp className="w-3.5 h-3.5 text-primary" /> : <ChevronDown className="w-3.5 h-3.5 text-primary" />;
}

/* ═══════════════════ Users Management Section ═══════════════════
   Esta é a aba original da página — preservada 100%.
   Só foi movida para dentro deste subcomponente.
   ═══════════════════════════════════════════════════════════════ */
function UsersManagementSection({ authUserEmail }: { authUserEmail: string | undefined }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [isLoading, setIsLoading] = useState(false);

  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [filterPlan, setFilterPlan] = useState("all");
  const [page, setPage] = useState(1);
  const [sortField, setSortField] = useState("id");
  const [sortOrder, setSortOrder] = useState("asc");

  const [editUser, setEditUser] = useState<AdminUser | null>(null);
  const [resetPwUser, setResetPwUser] = useState<AdminUser | null>(null);
  const [deleteUser, setDeleteUser] = useState<AdminUser | null>(null);
  const [resetPageUser, setResetPageUser] = useState<AdminUser | null>(null);
  const [showResetAll, setShowResetAll] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const fetchUsers = useCallback(async () => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(page), per_page: "50", sort_by: sortField, sort_order: sortOrder,
        ...(search && { search }), ...(filterPlan !== "all" && { plan_status: filterPlan }),
      });
      const res = await adminFetch(`/api/admin/users?${params}`);
      const data: UsersResponse = await res.json();
      if (res.ok) {
        setUsers(data.users || []);
        setTotal(data.total_users ?? data.total ?? 0);
        setTotalPages(data.total_pages ?? data.pages ?? 1);
      }
      else toast.error("Erro ao carregar usuários.");
    } catch { toast.error("Erro de rede."); }
    finally { setIsLoading(false); }
  }, [page, sortField, sortOrder, search, filterPlan]);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const handleSort = (field: string) => {
    if (field === sortField) setSortOrder((o) => (o === "asc" ? "desc" : "asc"));
    else { setSortField(field); setSortOrder("asc"); }
    setPage(1);
  };

  const handleSearch = (e: React.FormEvent) => { e.preventDefault(); setSearch(searchInput); setPage(1); };

  const handleToggleStatus = async (u: AdminUser) => {
    try {
      const res = await adminFetch(`/api/admin/users/${u.id}/status`, { method: "PUT", body: JSON.stringify({ is_active: !u.is_active }) });
      const data = await res.json();
      if (res.ok) { toast.success(data.msg || "Status atualizado!"); fetchUsers(); } else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
  };

  const handleDelete = async () => {
    if (!deleteUser) return;
    setActionLoading(true);
    try {
      const res = await adminFetch(`/api/admin/users/${deleteUser.id}`, { method: "DELETE" });
      const data = await res.json();
      if (res.ok) { toast.success(data.msg || "Usuário excluído!"); setDeleteUser(null); fetchUsers(); } else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setActionLoading(false); }
  };

  const handleResetPageCount = async () => {
    if (!resetPageUser) return;
    setActionLoading(true);
    try {
      const res = await adminFetch(`/api/admin/users/${resetPageUser.id}/reset-pages`, { method: "POST" });
      const data = await res.json();
      if (res.ok) { toast.success(data.msg || "Contagem zerada!"); setResetPageUser(null); fetchUsers(); } else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setActionLoading(false); }
  };

  const handleResetAll = async () => {
    setActionLoading(true);
    try {
      const res = await adminFetch("/api/admin/users/reset-pages", { method: "POST" });
      const data = await res.json();
      if (res.ok) { toast.success(data.msg || "Contagens zeradas!"); setShowResetAll(false); fetchUsers(); } else toast.error(data.msg || "Erro.");
    } catch { toast.error("Erro de rede."); }
    finally { setActionLoading(false); }
  };

  const planCounts = users.reduce((acc, u) => { const p = u.plan_status || "free"; acc[p] = (acc[p] || 0) + 1; return acc; }, {} as Record<string, number>);

  const columns = [
    { label: "ID", field: "id", w: "w-16" },
    { label: "E-mail", field: "email", w: "min-w-[200px]" },
    { label: "Status", field: "is_active", w: "w-24" },
    { label: "Plano", field: "plan_status", w: "w-36" },
    { label: "Páginas", field: "page_count", w: "w-24" },
    { label: "Role", field: "role", w: "w-20" },
    { label: "Ações", field: null as string | null, w: "min-w-[200px]" },
  ];

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Total", value: total, color: "text-foreground" },
          { label: "Premium", value: planCounts["premium"] || 0, color: "text-amber-400" },
          { label: "Padrão", value: planCounts["standard"] || 0, color: "text-primary" },
          { label: "Free", value: planCounts["free"] || 0, color: "text-muted-foreground" },
        ].map((s, i) => (
          <div key={i} className="bg-card border border-border/50 rounded-xl p-4 text-center">
            <p className="text-muted-foreground text-xs mb-1">{s.label}</p>
            <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="bg-card border border-border/50 rounded-xl p-4">
        <div className="flex flex-wrap items-center gap-3">
          <form onSubmit={handleSearch} className="flex items-center gap-2 flex-1 min-w-[200px]">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input type="text" placeholder="Buscar por e-mail..." value={searchInput} onChange={(e) => setSearchInput(e.target.value)}
                className="w-full pl-9 pr-3 py-2.5 rounded-lg bg-background/50 border border-border/50 text-foreground text-sm focus:outline-none focus:border-primary/60 focus:ring-1 focus:ring-primary/20 transition-all" />
            </div>
            <button type="submit" className="px-4 py-2.5 rounded-lg gradient-primary text-primary-foreground text-sm font-medium">
              <Search className="w-4 h-4" />
            </button>
          </form>

          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-muted-foreground" />
            <select value={filterPlan} onChange={(e) => { setFilterPlan(e.target.value); setPage(1); }}
              className="px-3 py-2.5 rounded-lg bg-background/50 border border-border/50 text-foreground text-sm focus:outline-none focus:border-primary/60 transition-all">
              <option value="all">Todos os planos</option>
              <option value="free">Free Trial</option>
              <option value="basic">Básico</option>
              <option value="standard">Padrão</option>
              <option value="premium">Premium</option>
              <option value="past_due">Pend. Pagamento</option>
              <option value="inactive">Inativo</option>
            </select>
          </div>

          <button onClick={fetchUsers} className="p-2.5 rounded-lg border border-border/50 text-muted-foreground hover:text-foreground hover:border-border transition-all" title="Atualizar">
            <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
          </button>

          <button onClick={() => setShowResetAll(true)} className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive hover:bg-destructive/20 text-sm font-medium transition-all whitespace-nowrap">
            <RotateCcw className="w-4 h-4" /> Zerar Todos
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="bg-card border border-border/50 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/50 bg-muted/30">
                {columns.map((col) => (
                  <th key={col.label} className={`px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider ${col.w} ${col.field ? "cursor-pointer hover:text-foreground" : ""}`}
                    onClick={() => col.field && handleSort(col.field)}>
                    <div className="flex items-center gap-1">
                      {col.label}
                      {col.field && <SortIcon field={col.field} sortField={sortField} sortOrder={sortOrder} />}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={columns.length} className="px-4 py-12 text-center"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground mx-auto" /></td></tr>
              ) : users.length === 0 ? (
                <tr><td colSpan={columns.length} className="px-4 py-12 text-center text-muted-foreground">Nenhum usuário encontrado.</td></tr>
              ) : (
                users.map((u) => (
                  <tr key={u.id} className="border-b border-border/30 last:border-0 hover:bg-muted/20 transition-colors">
                    <td className="px-4 py-3 text-muted-foreground font-mono text-xs">{u.id}</td>
                    <td className="px-4 py-3 text-foreground">{u.email}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${u.is_active ? "text-emerald-400" : "text-destructive"}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${u.is_active ? "bg-emerald-400" : "bg-destructive"}`} />
                        {u.is_active ? "Ativo" : "Inativo"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-medium border ${PLAN_COLORS[u.plan_status] || PLAN_COLORS.free}`}>
                        {PLAN_LABELS[u.plan_status] || u.plan_status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-foreground">{u.page_count}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs text-muted-foreground">{u.role}</span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <button onClick={() => setEditUser(u)} title="Editar" className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-all"><Edit3 className="w-4 h-4" /></button>
                        <button onClick={() => setResetPwUser(u)} title="Resetar senha" className="p-1.5 rounded-lg text-muted-foreground hover:text-amber-400 hover:bg-amber-400/10 transition-all"><KeyRound className="w-4 h-4" /></button>
                        <button onClick={() => handleToggleStatus(u)} disabled={u.email === authUserEmail} title={u.is_active ? "Desativar" : "Ativar"}
                          className={`p-1.5 rounded-lg transition-all disabled:opacity-30 disabled:cursor-not-allowed ${u.is_active ? "text-muted-foreground hover:text-destructive hover:bg-destructive/10" : "text-muted-foreground hover:text-emerald-400 hover:bg-emerald-400/10"}`}>
                          {u.is_active ? <UserX className="w-4 h-4" /> : <UserCheck className="w-4 h-4" />}
                        </button>
                        <button onClick={() => setResetPageUser(u)} title="Zerar contagem" className="p-1.5 rounded-lg text-muted-foreground hover:text-blue-400 hover:bg-blue-400/10 transition-all"><RotateCcw className="w-4 h-4" /></button>
                        <button onClick={() => setDeleteUser(u)} disabled={u.email === authUserEmail} title="Excluir"
                          className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all disabled:opacity-30 disabled:cursor-not-allowed"><Trash2 className="w-4 h-4" /></button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-border/50">
            <span className="text-muted-foreground text-xs">Página {page} de {totalPages} · {total} usuários</span>
            <div className="flex items-center gap-1">
              <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}
                className="p-1.5 rounded-lg border border-border/50 text-muted-foreground hover:text-foreground hover:border-border transition-all disabled:opacity-30 disabled:cursor-not-allowed">
                <ChevronLeft className="w-4 h-4" />
              </button>
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                const pg = Math.max(1, Math.min(totalPages - 4, page - 2)) + i;
                return (
                  <button key={pg} onClick={() => setPage(pg)}
                    className={`w-8 h-8 rounded-lg text-sm font-medium transition-all ${pg === page ? "gradient-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground hover:bg-muted/50"}`}>
                    {pg}
                  </button>
                );
              })}
              <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                className="p-1.5 rounded-lg border border-border/50 text-muted-foreground hover:text-foreground hover:border-border transition-all disabled:opacity-30 disabled:cursor-not-allowed">
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modals */}
      {editUser && <EditUserModal user={editUser} onClose={() => setEditUser(null)} onSuccess={fetchUsers} />}
      {resetPwUser && <ResetPasswordModal user={resetPwUser} onClose={() => setResetPwUser(null)} onSuccess={fetchUsers} />}
      {deleteUser && <ConfirmModal title="Excluir Usuário" message={`Tem certeza que deseja excluir ${deleteUser.email}? Esta ação é irreversível.`} confirmLabel="Excluir" onClose={() => setDeleteUser(null)} onConfirm={handleDelete} loading={actionLoading} />}
      {resetPageUser && <ConfirmModal title="Zerar Contagem" message={`Zerar contagem de páginas de ${resetPageUser.email}?`} confirmLabel="Zerar" onClose={() => setResetPageUser(null)} onConfirm={handleResetPageCount} loading={actionLoading} danger={false} />}
      {showResetAll && <ConfirmModal title="Zerar Todos os Usuários" message="Tem certeza que deseja zerar a contagem de páginas de TODOS os usuários? Esta ação é irreversível." confirmLabel="Zerar Todos" onClose={() => setShowResetAll(false)} onConfirm={handleResetAll} loading={actionLoading} />}
    </div>
  );
}

/* ═══════════════════ Main AdminPage (com abas) ═══════════════════ */
type AdminTab = "users" | "referrals" | "promotions" | "announcements" | "maintenance" | "organizations";

export default function AdminPage() {
  const navigate = useNavigate();
  const { logout, user: authUser } = useAuth();
  const [activeTab, setActiveTab] = useState<AdminTab>("users");

  const handleLogout = () => { logout(); navigate("/login"); };

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Header */}
      <header className="sticky top-0 z-40 border-b border-border/50 bg-card/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl gradient-primary flex items-center justify-center">
              <Shield className="w-5 h-5 text-primary-foreground" />
            </div>
            <div>
              <h1 className="text-foreground font-bold text-lg">Painel Admin</h1>
              <p className="text-muted-foreground text-xs">{authUser?.email}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => navigate("/app")} className="flex items-center gap-2 px-4 py-2 rounded-lg border border-border/50 text-muted-foreground hover:text-foreground hover:border-border transition-all text-sm">
              <LayoutDashboard className="w-4 h-4" /> Sistema
            </button>
            <button onClick={handleLogout} className="flex items-center gap-2 px-4 py-2 rounded-lg border border-destructive/30 text-destructive hover:bg-destructive/10 transition-all text-sm">
              <LogOut className="w-4 h-4" /> Sair
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        {/* ═══ Abas ═══ */}
        <div className="flex gap-1 border-b border-border/50 mb-6 overflow-x-auto">
          <TabButton
            active={activeTab === "users"}
            onClick={() => setActiveTab("users")}
            icon={<Users className="w-4 h-4" />}
          >
            Usuários
          </TabButton>
          <TabButton
            active={activeTab === "referrals"}
            onClick={() => setActiveTab("referrals")}
            icon={<UserPlus className="w-4 h-4" />}
          >
            Indicações
          </TabButton>
          <TabButton
            active={activeTab === "promotions"}
            onClick={() => setActiveTab("promotions")}
            icon={<Gift className="w-4 h-4" />}
          >
            Promoções
	  </TabButton>
          <TabButton
            active={activeTab === "announcements"}
            onClick={() => setActiveTab("announcements")}
            icon={<Megaphone className="w-4 h-4" />}
          >
            Avisos
          </TabButton>
	   <TabButton
            active={activeTab === "maintenance"}
            onClick={() => setActiveTab("maintenance")}
            icon={<Wrench className="w-4 h-4" />}
          >
            Manutenções
          </TabButton>
	  <TabButton
            active={activeTab === "organizations"}
            onClick={() => setActiveTab("organizations")}
            icon={<Building className="w-4 h-4" />}
          >
            Empresas
          </TabButton>
        </div>

        {/* ═══ Conteúdo da aba ativa ═══ */}
        {activeTab === "users"      && <UsersManagementSection authUserEmail={authUser?.email} />}
        {activeTab === "referrals"  && <AdminReferralsTab />}
        {activeTab === "promotions" && <AdminPromotionsTab />}
	{activeTab === "announcements"  && <AdminAnnouncementsTab />}
	{activeTab === "maintenance"   && <AdminMaintenanceTab />}
	{activeTab === "organizations" && <AdminOrganizationsTab />}
      </main>
    </div>
  );
}

/* ═══════════════════ TabButton helper ═══════════════════ */
function TabButton({
  active, onClick, icon, children,
}: {
  active: boolean;
  onClick: () => void;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-all whitespace-nowrap -mb-[1px] ${
        active
          ? "border-primary text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground"
      }`}
    >
      {icon}
      {children}
    </button>
  );
}
