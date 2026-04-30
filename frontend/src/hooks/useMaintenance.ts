// frontend/src/hooks/useMaintenance.ts
//
// Hook para detectar e acompanhar manutenção em curso.
// v2: polling mais agressivo + sync entre abas + cache localStorage.

import { useState, useEffect, useCallback, useRef } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export interface MaintenanceStatus {
  active: boolean;
  upcoming?: boolean;
  starts_at?: string | null;
  ends_at?: string | null;
  message?: string;
  is_emergency?: boolean;
}

const POLL_ACTIVE_MS = 30 * 1000;     // 30s quando em manutenção
const POLL_NORMAL_MS = 60 * 1000;     // 1 min quando normal (era 5min, ficou agressivo)
const STORAGE_KEY = "sp_maintenance_status";

function readCache(): MaintenanceStatus | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function writeCache(status: MaintenanceStatus) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(status));
  } catch {
    // ignore
  }
}

export function useMaintenance() {
  const [status, setStatus] = useState<MaintenanceStatus>(
    () => readCache() ?? { active: false }
  );
  const [isLoading, setIsLoading] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/maintenance/status`);
      if (!res.ok) {
        if (res.status === 503) {
          const data = await res.json().catch(() => ({}));
          const newStatus: MaintenanceStatus = {
            active: true,
            starts_at: data.starts_at,
            ends_at: data.ends_at,
            message: data.message || "Sistema em manutenção.",
          };
          setStatus(newStatus);
          writeCache(newStatus);
          return;
        }
        return;
      }
      const data: MaintenanceStatus = await res.json();
      setStatus(data);
      writeCache(data);
    } catch {
      // Silencioso
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Inicial: re-busca já no mount, sobrescrevendo o cache
  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Polling dinâmico (mais agressivo se manutenção)
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);

    const intervalMs = status.active ? POLL_ACTIVE_MS : POLL_NORMAL_MS;
    intervalRef.current = setInterval(fetchStatus, intervalMs);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchStatus, status.active]);

  // Visibilitychange: re-checa imediatamente quando aba volta
  useEffect(() => {
    const handler = () => {
      if (document.visibilityState === "visible") {
        fetchStatus();
      }
    };
    document.addEventListener("visibilitychange", handler);
    return () => document.removeEventListener("visibilitychange", handler);
  }, [fetchStatus]);

  // Sync entre abas: outra aba detectou manutenção, esta aba também sabe
  useEffect(() => {
    const handler = (e: StorageEvent) => {
      if (e.key !== STORAGE_KEY) return;
      if (e.newValue) {
        try {
          const parsed = JSON.parse(e.newValue);
          setStatus(parsed);
        } catch {
          // ignore
        }
      }
    };
    window.addEventListener("storage", handler);
    return () => window.removeEventListener("storage", handler);
  }, []);

  return { status, isLoading, refetch: fetchStatus };
}
