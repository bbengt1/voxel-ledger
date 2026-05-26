/**
 * Suggested storefronts for the supply ``place_of_purchase`` picker.
 * Sourced from the ``supplies.places_of_purchase`` setting so admins
 * can tweak the list without a code change.
 *
 * Same fetch/cache pattern as :mod:`materialTypes` — module-level
 * promise, fallback list for the initial render and any failed fetch.
 */
import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";

const SETTING_KEY = "supplies.places_of_purchase";

export const FALLBACK_PLACES_OF_PURCHASE: readonly string[] = [
  "Amazon",
  "eBay",
  "Home Depot",
  "Lowes",
  "Walmart",
  "Target",
  "Costco",
  "AliExpress",
  "Etsy",
  "Best Buy",
  "Micro Center",
  "Local store",
];

let cached: readonly string[] | null = null;
let inFlight: Promise<readonly string[]> | null = null;

function normalize(raw: unknown): readonly string[] {
  if (!Array.isArray(raw)) return FALLBACK_PLACES_OF_PURCHASE;
  const cleaned = raw
    .map((v) => (typeof v === "string" ? v.trim() : ""))
    .filter((v) => v.length > 0);
  return cleaned.length > 0 ? cleaned : FALLBACK_PLACES_OF_PURCHASE;
}

async function fetchPlaces(): Promise<readonly string[]> {
  if (cached !== null) return cached;
  if (inFlight !== null) return inFlight;
  inFlight = apiClient
    .get<{ value: unknown }>(
      `/api/v1/settings/${encodeURIComponent(SETTING_KEY)}`,
    )
    .then((res) => {
      const list = normalize(res.data.value);
      cached = list;
      return list;
    })
    .catch(() => {
      cached = FALLBACK_PLACES_OF_PURCHASE;
      return FALLBACK_PLACES_OF_PURCHASE;
    })
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

export function usePlacesOfPurchase(): readonly string[] {
  const [places, setPlaces] = useState<readonly string[]>(
    cached ?? FALLBACK_PLACES_OF_PURCHASE,
  );
  useEffect(() => {
    let cancelled = false;
    fetchPlaces().then((list) => {
      if (!cancelled) setPlaces(list);
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return places;
}

export function invalidatePlacesOfPurchaseCache(): void {
  cached = null;
}
