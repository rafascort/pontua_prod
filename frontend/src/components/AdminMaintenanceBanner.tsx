// frontend/src/components/AdminMaintenanceBanner.tsx
//
// Banner amarelo mostrado APENAS para admin quando há manutenção ativa.
// Aparece no topo de toda página, abaixo do AppHeader.

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Wrench, ExternalLink } from "lucide-react";
import { useMaintenance } from "@/hooks/useMaintenance";
import { useAuth } from "@/contexts/AuthContext";

const AdminMaintenanceBanner = () => {
  const { status } = useMaintenance();
  const { user } = useAuth();
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60_000); // atualiza a cada 1min
    return () => clearInterval(t);
  }, []);

  // Só aparece para admin durante manutenção ativa
  if (!status.active) return null;
  if (user?.role !== "admin") return null;

  const endsAt = status.ends_at ? new Date(status.ends_at) : null;
  const remainingMs = endsAt ? Math.max(0, endsAt.getTime() - now.getTime()) : 0;
  const remainingMin = Math.floor(remainingMs / 60000);
  const remainingHours = Math.floor(remainingMin / 60);
  const remainingMinPart = remainingMin % 60;

  const formatRemaining = () => {
    if (remainingMs <= 0) return "encerrando";
    if (remainingHours > 0) {
      return `${remainingHours}h ${remainingMinPart.toString().padStart(2, "0")}min restantes`;
    }
    return `${remainingMin} min restantes`;
  };

  return (
    <div className="bg-amber-500/10 border-b border-amber-500/30 py-2 px-4">
      <div className="container mx-auto flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400 flex-1 min-w-[200px]">
          <Wrench className="w-4 h-4 shrink-0 animate-pulse" />
          <span>
            <strong>Sistema em manutenção</strong>
            {endsAt && (
              <>
                {" "}até {endsAt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
                {" "}({formatRemaining()})
              </>
            )}
            <span className="hidden sm:inline">
              . Você está vendo como admin.
            </span>
          </span>
        </div>

        <Link
          to="/admin"
          className="text-xs font-semibold text-amber-700 dark:text-amber-400 hover:underline inline-flex items-center gap-1"
        >
          Painel de manutenção
          <ExternalLink className="w-3 h-3" />
        </Link>
      </div>
    </div>
  );
};

export default AdminMaintenanceBanner;
