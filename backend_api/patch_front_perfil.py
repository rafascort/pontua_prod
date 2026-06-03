# -*- coding: utf-8 -*-
#
# Patch do FRONTEND para coletar/exibir/editar Nome, Sobrenome, Telefone e Empresa.
# Arquivos tocados (todos com backup .pre_perfil):
#   - src/lib/api.ts            (register passa o objeto profile)
#   - src/contexts/AuthContext.tsx (register repassa profile)
#   - src/pages/CadastroPage.tsx (4 campos novos + mascara de telefone + validacao)
#   - src/pages/AdminPage.tsx    (interface + botao Detalhes + modal de detalhes + edicao)
#
# Uso:  python3 patch_front_perfil.py
# Depois: cd /opt/pontua/AutoPonto/frontend && npm run build && sudo cp -r dist/* /var/www/pontua/
#
# Cada edicao reporta [ok] / [skip] (ja aplicada) / [FALHOU] (anchor nao encontrado).
# Se algo der [FALHOU], me avise QUAL e eu ajusto so aquele trecho. O script nunca
# escreve um arquivo se nenhuma edicao bateu, e sempre gera backup antes de salvar.

import shutil

BASE = "/opt/pontua/AutoPonto/frontend"
report = []


def edit(src, label, old, new, guard):
    if guard in src:
        report.append("  [skip] " + label + " (ja aplicado)")
        return src
    if old in src:
        report.append("  [ok]   " + label)
        return src.replace(old, new, 1)
    report.append("  [FALHOU] " + label + " -- anchor nao encontrado")
    return src


def process(relpath, edits):
    path = BASE + relpath
    report.append("")
    report.append("== " + relpath + " ==")
    try:
        src = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        report.append("  [FALHOU] arquivo nao encontrado: " + path)
        return
    orig = src
    for (label, old, new, guard) in edits:
        src = edit(src, label, old, new, guard)
    if src != orig:
        shutil.copy(path, path + ".pre_perfil")
        open(path, "w", encoding="utf-8").write(src)
        report.append("  -> salvo. backup: " + path + ".pre_perfil")
    else:
        report.append("  -> nada alterado (nenhuma edicao bateu)")


PROFILE_TS = "{ first_name?: string; last_name?: string; phone?: string; company_name?: string }"

# ─────────────────────────────────────────────────────────────────────
# 1) src/lib/api.ts
# ─────────────────────────────────────────────────────────────────────
process("/src/lib/api.ts", [
    (
        "register(): troca param 'name' por 'profile'",
        r'''    refCode?: string | null,
    name?: string,
  ): Promise<{ msg: string }> {''',
        r'''    refCode?: string | null,
    profile?: { first_name?: string; last_name?: string; phone?: string; company_name?: string },
  ): Promise<{ msg: string }> {''',
        "profile?: { first_name",
    ),
    (
        "register(): body inclui os campos de perfil",
        r'''        ...(name ? { name } : {}),
        ...(refCode ? { ref_code: refCode } : {}),''',
        r'''        ...(refCode ? { ref_code: refCode } : {}),
        ...(profile?.first_name   ? { first_name:   profile.first_name }   : {}),
        ...(profile?.last_name    ? { last_name:    profile.last_name }    : {}),
        ...(profile?.phone        ? { phone:        profile.phone }        : {}),
        ...(profile?.company_name ? { company_name: profile.company_name } : {}),''',
        "profile?.first_name",
    ),
])

# ─────────────────────────────────────────────────────────────────────
# 2) src/contexts/AuthContext.tsx
# ─────────────────────────────────────────────────────────────────────
process("/src/contexts/AuthContext.tsx", [
    (
        "tipo register na interface",
        r'''  register: (email: string, password: string, refCode?: string | null) => Promise<string>;''',
        r'''  register: (email: string, password: string, refCode?: string | null, profile?: { first_name?: string; last_name?: string; phone?: string; company_name?: string }) => Promise<string>;''',
        "profile?: { first_name",
    ),
    (
        "implementacao register repassa profile",
        r'''  const register = async (email: string, password: string, refCode?: string | null) => {
    const result = await api.register(email, password, refCode);
    return result.msg;
  };''',
        r'''  const register = async (email: string, password: string, refCode?: string | null, profile?: { first_name?: string; last_name?: string; phone?: string; company_name?: string }) => {
    const result = await api.register(email, password, refCode, profile);
    return result.msg;
  };''',
        "api.register(email, password, refCode, profile)",
    ),
])

# ─────────────────────────────────────────────────────────────────────
# 3) src/pages/CadastroPage.tsx
# ─────────────────────────────────────────────────────────────────────
process("/src/pages/CadastroPage.tsx", [
    (
        "imports lucide (User, Phone, Building)",
        r'''import { Mail, Lock, Sparkles, UserPlus, ArrowLeft, MessageCircle, CheckCircle, RefreshCw, Users } from "lucide-react";''',
        r'''import { Mail, Lock, Sparkles, UserPlus, ArrowLeft, MessageCircle, CheckCircle, RefreshCw, Users, User, Phone, Building } from "lucide-react";''',
        "Users, User, Phone, Building",
    ),
    (
        "helper formatPhoneBR",
        r'''const CadastroPage = () => {''',
        r'''function formatPhoneBR(v: string): string {
  const d = v.replace(/\D/g, "").slice(0, 11);
  if (!d) return "";
  if (d.length <= 2) return `(${d}`;
  if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`;
  if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
}

const CadastroPage = () => {''',
        "function formatPhoneBR",
    ),
    (
        "estados firstName/lastName/phone/company",
        r'''  const [confirmPassword, setConfirmPassword] = useState("");''',
        r'''  const [confirmPassword, setConfirmPassword] = useState("");
  const [firstName,       setFirstName]       = useState("");
  const [lastName,        setLastName]        = useState("");
  const [phone,           setPhone]           = useState("");
  const [company,         setCompany]         = useState("");''',
        "const [firstName,       setFirstName]",
    ),
    (
        "validacao obrigatoria (nome/sobrenome/telefone)",
        r'''    if (password !== confirmPassword) { toast.error("As senhas não coincidem."); return; }''',
        r'''    if (!firstName.trim()) { toast.error("Informe seu nome."); return; }
    if (!lastName.trim())  { toast.error("Informe seu sobrenome."); return; }
    if (phone.replace(/\D/g, "").length < 10) { toast.error("Informe um telefone válido com DDD."); return; }
    if (password !== confirmPassword) { toast.error("As senhas não coincidem."); return; }''',
        "Informe seu nome.",
    ),
    (
        "register() envia profile",
        r'''      await register(email, password, refCode);''',
        r'''      await register(email, password, refCode, {
        first_name:   firstName.trim(),
        last_name:    lastName.trim(),
        phone:        phone.trim(),
        company_name: company.trim() || undefined,
      });''',
        "first_name:   firstName.trim()",
    ),
    (
        "campos Nome + Sobrenome no inicio do form",
        r'''        <form onSubmit={handleCadastro} className="flex flex-col gap-4">''',
        r'''        <form onSubmit={handleCadastro} className="flex flex-col gap-4">
          <div>
            <label className="text-sm font-medium text-foreground mb-2 block">Nome</label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type="text"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                placeholder="João"
                className="w-full pl-10 pr-4 py-3 bg-background/60 border border-border rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                required
                autoComplete="given-name"
              />
            </div>
          </div>
          <div>
            <label className="text-sm font-medium text-foreground mb-2 block">Sobrenome</label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type="text"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                placeholder="Pereira"
                className="w-full pl-10 pr-4 py-3 bg-background/60 border border-border rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                required
                autoComplete="family-name"
              />
            </div>
          </div>''',
        'autoComplete="given-name"',
    ),
    (
        "campos Telefone + Empresa apos o E-mail",
        r'''                autoComplete="email"
              />
            </div>
          </div>''',
        r'''                autoComplete="email"
              />
            </div>
          </div>
          <div>
            <label className="text-sm font-medium text-foreground mb-2 block">Telefone</label>
            <div className="relative">
              <Phone className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type="text"
                inputMode="tel"
                value={phone}
                onChange={(e) => setPhone(formatPhoneBR(e.target.value))}
                placeholder="(54) 99999-9999"
                className="w-full pl-10 pr-4 py-3 bg-background/60 border border-border rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                required
                autoComplete="tel"
              />
            </div>
          </div>
          <div>
            <label className="text-sm font-medium text-foreground mb-2 block">Empresa <span className="text-muted-foreground font-normal">(opcional)</span></label>
            <div className="relative">
              <Building className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type="text"
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                placeholder="Onde você trabalha"
                className="w-full pl-10 pr-4 py-3 bg-background/60 border border-border rounded-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all"
                autoComplete="organization"
              />
            </div>
          </div>''',
        'autoComplete="tel"',
    ),
])

# ─────────────────────────────────────────────────────────────────────
# 4) src/pages/AdminPage.tsx
# ─────────────────────────────────────────────────────────────────────
USER_DETAILS_MODAL = r'''/* ═══════════════════ User Details Modal ═══════════════════ */
function UserDetailsModal({ user, onClose, onEdit }: { user: AdminUser; onClose: () => void; onEdit: () => void }) {
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ").trim() || user.name || "";
  const display = fullName || user.email;
  const initials = (fullName ? fullName.split(/\s+/) : user.email.split(/[.@]/))
    .filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("");
  const rows: { icon: JSX.Element; label: string; value: string; muted?: boolean }[] = [
    { icon: <Phone className="w-4 h-4" />, label: "Telefone", value: user.phone || "Não informado", muted: !user.phone },
    { icon: <Building className="w-4 h-4" />, label: "Empresa", value: user.company_name || "Não informado", muted: !user.company_name },
    { icon: <Shield className="w-4 h-4" />, label: "Plano", value: PLAN_LABELS[user.plan_status] || user.plan_status },
    { icon: <LayoutDashboard className="w-4 h-4" />, label: "Páginas usadas", value: String(user.page_count) },
    { icon: <Check className="w-4 h-4" />, label: "Status", value: user.is_active ? "Ativo" : "Inativo", muted: !user.is_active },
    { icon: <UserCheck className="w-4 h-4" />, label: "Role", value: user.role },
    { icon: <Gift className="w-4 h-4" />, label: "ID", value: String(user.id) },
  ];
  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-card border border-border rounded-2xl overflow-hidden shadow-xl">
        <div className="flex items-center justify-between p-5 border-b border-border/50">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-full bg-primary/10 border border-primary/20 text-primary flex items-center justify-center font-semibold">{initials}</div>
            <div>
              <p className="text-foreground font-semibold leading-tight">{display}</p>
              <p className="text-sm text-primary">{user.email}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5">
          {rows.map((r) => (
            <div key={r.label} className="flex items-center justify-between py-2.5 border-b border-border/30 last:border-0">
              <span className="flex items-center gap-2 text-sm text-muted-foreground">{r.icon}{r.label}</span>
              <span className={`text-sm font-medium ${r.muted ? "italic text-muted-foreground" : "text-foreground"}`}>{r.value}</span>
            </div>
          ))}
          <button onClick={onEdit} className="mt-5 w-full gradient-primary text-primary-foreground py-2.5 rounded-lg font-medium flex items-center justify-center gap-2 hover:shadow-lg hover:shadow-primary/25 transition-all">
            <Edit3 className="w-4 h-4" /> Editar usuário
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
}

function EditUserModal({ user, onClose, onSuccess }: { user: AdminUser; onClose: () => void; onSuccess: () => void }) {'''

EDIT_MODAL_FIELDS = r'''        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm font-medium text-foreground mb-1.5 block">Nome</label>
              <input type="text" value={firstName} onChange={(e) => setFirstName(e.target.value)} disabled={loading}
                className="w-full px-3 py-2.5 rounded-lg bg-background/50 border border-border/50 text-foreground text-sm focus:outline-none focus:border-primary/60 focus:ring-1 focus:ring-primary/20 transition-all" />
            </div>
            <div>
              <label className="text-sm font-medium text-foreground mb-1.5 block">Sobrenome</label>
              <input type="text" value={lastName} onChange={(e) => setLastName(e.target.value)} disabled={loading}
                className="w-full px-3 py-2.5 rounded-lg bg-background/50 border border-border/50 text-foreground text-sm focus:outline-none focus:border-primary/60 focus:ring-1 focus:ring-primary/20 transition-all" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm font-medium text-foreground mb-1.5 block">Telefone</label>
              <input type="text" value={phone} onChange={(e) => setPhone(e.target.value)} disabled={loading}
                className="w-full px-3 py-2.5 rounded-lg bg-background/50 border border-border/50 text-foreground text-sm focus:outline-none focus:border-primary/60 focus:ring-1 focus:ring-primary/20 transition-all" />
            </div>
            <div>
              <label className="text-sm font-medium text-foreground mb-1.5 block">Empresa</label>
              <input type="text" value={company} onChange={(e) => setCompany(e.target.value)} disabled={loading}
                className="w-full px-3 py-2.5 rounded-lg bg-background/50 border border-border/50 text-foreground text-sm focus:outline-none focus:border-primary/60 focus:ring-1 focus:ring-primary/20 transition-all" />
            </div>
          </div>'''

process("/src/pages/AdminPage.tsx", [
    (
        "imports lucide (Eye, Phone)",
        r'''  Gift, UserPlus, Megaphone, Wrench, Building,''',
        r'''  Gift, UserPlus, Megaphone, Wrench, Building, Eye, Phone,''',
        "Building, Eye, Phone,",
    ),
    (
        "interface AdminUser (+4 campos)",
        r'''  name?: string;''',
        r'''  name?: string;
  first_name?: string | null;
  last_name?: string | null;
  phone?: string | null;
  company_name?: string | null;''',
        "first_name?: string | null;",
    ),
    (
        "UserDetailsModal: definicao do componente",
        r'''function EditUserModal({ user, onClose, onSuccess }: { user: AdminUser; onClose: () => void; onSuccess: () => void }) {''',
        USER_DETAILS_MODAL,
        "function UserDetailsModal",
    ),
    (
        "EditUserModal: estados de perfil",
        r'''  const [pageCount, setPageCount] = useState(String(user.page_count));''',
        r'''  const [pageCount, setPageCount] = useState(String(user.page_count));
  const [firstName, setFirstName] = useState(user.first_name || "");
  const [lastName, setLastName] = useState(user.last_name || "");
  const [phone, setPhone] = useState(user.phone || "");
  const [company, setCompany] = useState(user.company_name || "");''',
        "const [firstName, setFirstName] = useState(user.first_name",
    ),
    (
        "EditUserModal: PUT body inclui perfil",
        r'''        body: JSON.stringify({ email, role, plan_status: planStatus, page_count: count }),''',
        r'''        body: JSON.stringify({ email, role, plan_status: planStatus, page_count: count, first_name: firstName, last_name: lastName, phone, company_name: company }),''',
        "first_name: firstName, last_name: lastName, phone, company_name: company",
    ),
    (
        "EditUserModal: campos no formulario",
        r'''        <form onSubmit={handleSubmit} className="p-5 space-y-4">''',
        EDIT_MODAL_FIELDS,
        'value={firstName} onChange={(e) => setFirstName',
    ),
    (
        "estado detailUser",
        r'''  const [editUser, setEditUser] = useState<AdminUser | null>(null);''',
        r'''  const [editUser, setEditUser] = useState<AdminUser | null>(null);
  const [detailUser, setDetailUser] = useState<AdminUser | null>(null);''',
        "const [detailUser, setDetailUser]",
    ),
    (
        "botao Detalhes (olho) na celula de Acoes",
        r'''                        <button onClick={() => setEditUser(u)} title="Editar" className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-all"><Edit3 className="w-4 h-4" /></button>''',
        r'''                        <button onClick={() => setDetailUser(u)} title="Detalhes" className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-all"><Eye className="w-4 h-4" /></button>
                        <button onClick={() => setEditUser(u)} title="Editar" className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-all"><Edit3 className="w-4 h-4" /></button>''',
        'onClick={() => setDetailUser(u)}',
    ),
    (
        "render do UserDetailsModal",
        r'''      {editUser && <EditUserModal user={editUser} onClose={() => setEditUser(null)} onSuccess={fetchUsers} />}''',
        r'''      {editUser && <EditUserModal user={editUser} onClose={() => setEditUser(null)} onSuccess={fetchUsers} />}
      {detailUser && <UserDetailsModal user={detailUser} onClose={() => setDetailUser(null)} onEdit={() => { setEditUser(detailUser); setDetailUser(null); }} />}''',
        "detailUser && <UserDetailsModal",
    ),
])

print("\n".join(report))
print("")
print("Concluido. Se nao houve [FALHOU], rode:")
print('  cd ' + BASE + ' && npm run build && sudo cp -r dist/* /var/www/pontua/')
print("")
print("Para desfazer (restaurar backups):")
print('  for f in src/lib/api.ts src/contexts/AuthContext.tsx src/pages/CadastroPage.tsx src/pages/AdminPage.tsx; do cp "' + BASE + '/$f.pre_perfil" "' + BASE + '/$f"; done')
