// frontend/src/hooks/useAnnouncements.ts
//
// Busca avisos pendentes para o usuário logado.
// Re-checa em: mount + visibilitychange + polling (3min) + mudança de token.
// v2: detecta login fresco (token recém-salvo) e refaz busca.

import { useState, useEffect, useCallback, useRef } from "react";

export type AnnouncementSeverity = "info" | "warning" | "critical" | "news";
export type AnnouncementFrequency = "once" | "every_session";

export interface Announcement {
  id: number;
  title: string;
  message: string;
  severity: AnnouncementSeverity;
  frequency: AnnouncementFrequency;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const POLL_INTERVAL_MS = 3 * 60 * 1000; // 3 minutos
const TOKEN_CHECK_MS = 1000; // checa mudança de token a cada 1s

function getToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("jwt_token");
}

export function useAnnouncements() {
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastTokenRef = useRef<string | null>(null);

  const fetchPending = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setAnnouncements([]);
      setIsLoading(false);
      return;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/api/announcements/pending`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        setAnnouncements([]);
        return;
      }
      const data = await res.json();
      setAnnouncements(data.announcements || []);
    } catch {
      setAnnouncements([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Mount inicial — guarda o token atual e dispara a busca
  useEffect(() => {
    lastTokenRef.current = getToken();
    fetchPending();
  }, [fetchPending]);

  // ── DETECÇÃO DE TOKEN NOVO (login fresco) ─────────────────────────
  // Verifica a cada 1s se o token mudou. Se mudou (login fresco ou
  // troca de usuário), refaz a busca imediatamente.
  useEffect(() => {
    const checker = setInterval(() => {
      const currentToken = getToken();
      if (currentToken !== lastTokenRef.current) {
        lastTokenRef.current = currentToken;
        if (currentToken) {
          // Token novo apareceu → user acabou de logar
          fetchPending();
        } else {
          // Token sumiu → user deslogou, limpa a lista
          setAnnouncements([]);
        }
      }
    }, TOKEN_CHECK_MS);

    return () => clearInterval(checker);
  }, [fetchPending]);

  // Também escuta o evento 'storage' para mudanças em outras abas
  useEffect(() => {
    const handler = (e: StorageEvent) => {
      if (e.key === "access_token" || e.key === "jwt_token") {
        const newToken = getToken();
        lastTokenRef.current = newToken;
        if (newToken) {
          fetchPending();
        } else {
          setAnnouncements([]);
        }
      }
    };
    window.addEventListener("storage", handler);
    return () => window.removeEventListener("storage", handler);
  }, [fetchPending]);

  // Polling de 3min enquanto a aba está visível
  useEffect(() => {
    const startPolling = () => {
      if (intervalRef.current) return;
      intervalRef.current = setInterval(fetchPending, POLL_INTERVAL_MS);
    };
    const stopPolling = () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };

    if (document.visibilityState === "visible") {
      startPolling();
    }

    return () => stopPolling();
  }, [fetchPending]);

  // visibilitychange: quando a aba volta a ficar visível, re-checa
  useEffect(() => {
    const handler = () => {
      if (document.visibilityState === "visible") {
        fetchPending();
        if (!intervalRef.current) {
          intervalRef.current = setInterval(fetchPending, POLL_INTERVAL_MS);
        }
      } else {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    };
    document.addEventListener("visibilitychange", handler);
    return () => document.removeEventListener("visibilitychange", handler);
  }, [fetchPending]);

  return { announcements, isLoading, refetch: fetchPending };
}

export async function acknowledgeAnnouncement(id: number): Promise<boolean> {
  const token = getToken();
  if (!token) return false;
  try {
    const res = await fetch(
      `${API_BASE_URL}/api/announcements/${id}/acknowledge`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      }
    );
    return res.ok;
  } catch {
    return false;
  }
}
