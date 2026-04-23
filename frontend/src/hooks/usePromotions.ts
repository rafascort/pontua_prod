// frontend/src/hooks/usePromotions.ts
//
// Busca promoções ativas para o usuário e trackeia eventos (impressões/cliques).

import { useState, useEffect, useCallback } from "react";

export type CtaType = "none" | "contact" | "link" | "code";
export type PromotionStatus = "live" | "scheduled" | "expired" | "inactive";

export interface Promotion {
  id: number;
  title: string;
  description: string;
  badge_label: string;
  badge_color: string;
  icon: string;
  discount_hint: string | null;
  cta_type: CtaType;
  cta_value: string | null;
  cta_label: string | null;
  priority: number;
  active: boolean;
  starts_at: string | null;
  ends_at: string | null;
  status: PromotionStatus;
  created_at: string | null;
  updated_at: string | null;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function getToken() {
  return localStorage.getItem("access_token") || localStorage.getItem("jwt_token");
}

export function usePromotions() {
  const [promotions, setPromotions] = useState<Promotion[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchPromotions = useCallback(async () => {
    setIsLoading(true);
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE_URL}/api/promotions/active`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      setPromotions(data.promotions || []);
    } catch {
      setPromotions([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPromotions();
  }, [fetchPromotions]);

  return { promotions, isLoading, refetch: fetchPromotions };
}

/** Registra um evento de métrica sem bloquear a UI (fire-and-forget). */
export async function trackPromotionEvent(
  promotionId: number,
  eventType: "impression" | "cta_click",
): Promise<void> {
  try {
    const token = getToken();
    if (!token) return;
    await fetch(`${API_BASE_URL}/api/promotions/${promotionId}/track`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ event_type: eventType }),
      keepalive: true,
    });
  } catch {
    // ignora falhas de tracking
  }
}
