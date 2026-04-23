// frontend/src/hooks/useReferralCapture.ts
//
// Captura `?ref=CODIGO` da URL e salva no localStorage por 30 dias.
// Usar em componentes raiz (App.tsx, LandingPage, CadastroPage).

import { useEffect } from "react";

const STORAGE_KEY = "sp_referral_code";
const TIMESTAMP_KEY = "sp_referral_ts";
const VALIDITY_DAYS = 30;

export function useReferralCapture(): void {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ref = params.get("ref");
    if (!ref) return;

    const cleaned = ref.trim().toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 20);
    if (cleaned.length < 3) return;

    try {
      localStorage.setItem(STORAGE_KEY, cleaned);
      localStorage.setItem(TIMESTAMP_KEY, String(Date.now()));
    } catch {
      // localStorage desabilitado — ignora
    }
  }, []);
}

export function getStoredReferralCode(): string | null {
  try {
    const code = localStorage.getItem(STORAGE_KEY);
    const tsRaw = localStorage.getItem(TIMESTAMP_KEY);
    if (!code || !tsRaw) return null;

    const ts = Number(tsRaw);
    const ageMs = Date.now() - ts;
    const maxAgeMs = VALIDITY_DAYS * 24 * 60 * 60 * 1000;

    if (ageMs > maxAgeMs) {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(TIMESTAMP_KEY);
      return null;
    }
    return code;
  } catch {
    return null;
  }
}

export function clearStoredReferralCode(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(TIMESTAMP_KEY);
  } catch {
    // ignora
  }
}
