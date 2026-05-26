import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";

const SETTING_KEY = "display.currency";

let cachedCurrency: string | null = null;
let inFlight: Promise<string> | null = null;

async function fetchCurrency(): Promise<string> {
  if (cachedCurrency !== null) return cachedCurrency;
  if (inFlight !== null) return inFlight;
  inFlight = apiClient
    .get<{ value: string }>(
      `/api/v1/settings/${encodeURIComponent(SETTING_KEY)}`,
    )
    .then((res) => {
      const code =
        typeof res.data.value === "string" ? res.data.value.toUpperCase() : "USD";
      cachedCurrency = code;
      return code;
    })
    .catch(() => {
      cachedCurrency = "USD";
      return "USD";
    })
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

export function useCurrency(): string {
  const [currency, setCurrency] = useState<string>(cachedCurrency ?? "USD");
  useEffect(() => {
    let cancelled = false;
    fetchCurrency().then((code) => {
      if (!cancelled) setCurrency(code);
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return currency;
}

export function formatCurrency(
  amount: number | string | null | undefined,
  currency: string,
): string {
  if (amount === null || amount === undefined || amount === "") return "";
  const value = typeof amount === "number" ? amount : Number(amount);
  if (!Number.isFinite(value)) return String(amount);
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
    }).format(value);
  } catch {
    // Invalid currency code → fall back to USD-formatted output.
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: "USD",
    }).format(value);
  }
}
