// frontend/src/hooks/useReferralStats.ts
//
// Busca as estatísticas de indicação do usuário logado.
// Usa endpoints /api/referral/stats e /api/referral/history.

import { useState, useEffect, useCallback } from "react";

export interface ReferralStats {
  referral_code: string;
  referral_link: string;
  converted_count: number;
  pending_count: number;
  discount_credits: number;
  active_discount_pct: number;
  next_month_discount_pct: number;
  max_monthly_discount_pct: number;
  pct_per_conversion: number;
}

export interface ReferralHistoryItem {
  id: number;
  referred_email_masked: string;
  status: "pending" | "converted" | "expired";
  plan: string | null;
  discount_pct: number;
  created_at: string | null;
  converted_at: string | null;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function getToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("jwt_token");
}

export function useReferralStats() {
  const [stats, setStats] = useState<ReferralStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE_URL}/api/referral/stats`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      const data: ReferralStats = await res.json();
      setStats(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao carregar");
      setStats(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  return { stats, isLoading, error, refetch: fetchStats };
}

export function useReferralHistory() {
  const [items, setItems] = useState<ReferralHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchHistory = useCallback(async () => {
    setIsLoading(true);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE_URL}/api/referral/history`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      setItems(data.referrals || []);
    } catch {
      setItems([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  return { items, isLoading, refetch: fetchHistory };
}
