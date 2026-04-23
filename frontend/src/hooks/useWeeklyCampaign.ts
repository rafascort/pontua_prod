// frontend/src/hooks/useWeeklyCampaign.ts
//
// Controla a exibição do modal de campanhas (1x por semana após login).
// Persiste no localStorage a data da última exibição.

import { useState, useEffect, useCallback } from "react";

const STORAGE_KEY = "sp_campaign_last_shown";
const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;

export function useWeeklyCampaign() {
  const [shouldShow, setShouldShow] = useState(false);

  useEffect(() => {
    try {
      const lastRaw = localStorage.getItem(STORAGE_KEY);
      if (!lastRaw) {
        setShouldShow(true);
        return;
      }
      const last = Number(lastRaw);
      if (Number.isNaN(last)) {
        setShouldShow(true);
        return;
      }
      const elapsed = Date.now() - last;
      setShouldShow(elapsed >= SEVEN_DAYS_MS);
    } catch {
      setShouldShow(false);
    }
  }, []);

  const dismiss = useCallback(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(Date.now()));
    } catch {
      // ignora
    }
    setShouldShow(false);
  }, []);

  const forceShow = useCallback(() => {
    setShouldShow(true);
  }, []);

  return { shouldShow, dismiss, forceShow };
}
