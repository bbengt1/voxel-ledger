/**
 * Common 3D-printing filament types. Sourced from the
 * ``materials.types`` setting so an admin can add specialty resins or
 * in-house blends from the settings page without a code change.
 *
 * A static fallback covers the initial render and any failed fetch so
 * the picker is never empty. The backend material_type column is
 * free-text, so custom entries always validate even if they aren't in
 * this list.
 */
import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";

const SETTING_KEY = "materials.types";

export const FALLBACK_MATERIAL_TYPES: readonly string[] = [
  "PLA",
  "PLA+",
  "Silk PLA",
  "PETG",
  "ABS",
  "ASA",
  "TPU",
  "TPE",
  "Nylon",
  "PC",
  "PVA",
  "HIPS",
  "Carbon Fiber",
  "Wood Fill",
  "PEEK",
  "PEI",
];

let cached: readonly string[] | null = null;
let inFlight: Promise<readonly string[]> | null = null;

function normalize(raw: unknown): readonly string[] {
  if (!Array.isArray(raw)) return FALLBACK_MATERIAL_TYPES;
  const cleaned = raw
    .map((v) => (typeof v === "string" ? v.trim() : ""))
    .filter((v) => v.length > 0);
  return cleaned.length > 0 ? cleaned : FALLBACK_MATERIAL_TYPES;
}

async function fetchMaterialTypes(): Promise<readonly string[]> {
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
      cached = FALLBACK_MATERIAL_TYPES;
      return FALLBACK_MATERIAL_TYPES;
    })
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

export function useMaterialTypes(): readonly string[] {
  const [types, setTypes] = useState<readonly string[]>(
    cached ?? FALLBACK_MATERIAL_TYPES,
  );
  useEffect(() => {
    let cancelled = false;
    fetchMaterialTypes().then((list) => {
      if (!cancelled) setTypes(list);
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return types;
}

/** Force the next ``useMaterialTypes`` consumer to refetch. */
export function invalidateMaterialTypesCache(): void {
  cached = null;
}
