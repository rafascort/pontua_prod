// frontend/src/pages/AdminEmailsPage.tsx
//
// Casca fina em volta do AdminEmailsTab, para o acesso direto por URL.
// A logica toda vive no componente — assim a aba do painel e esta pagina
// nunca saem de sincronia.
import { useNavigate } from "react-router-dom";
import AdminEmailsTab from "../components/AdminEmailsTab";

export default function AdminEmailsPage() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-background text-foreground p-6">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={() => navigate("/admin")}
            className="p-2 rounded-lg border border-border/50 text-muted-foreground hover:text-foreground transition-all"
            title="Voltar ao painel"
          >
            <i className="ti ti-arrow-left" />
          </button>
          <h1 className="text-2xl font-bold">E-mails do ciclo de vida</h1>
        </div>
        <AdminEmailsTab />
      </div>
    </div>
  );
}
