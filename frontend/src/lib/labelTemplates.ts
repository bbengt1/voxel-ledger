/**
 * Label-template registry.
 *
 * Each template captures the physical dimensions of an Avery-style
 * label sheet so the product-labels page can lay out a grid that
 * matches the operator's stock. The settings registry stores the
 * chosen template's ``id``; the frontend looks up dimensions here.
 *
 * Adding a new template: append an entry to ``LABEL_TEMPLATES`` and
 * the dropdown in the admin settings page picks it up automatically.
 */
import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";

const SETTING_KEY = "labels.template";

export interface LabelTemplate {
  id: string;
  name: string;
  /** ``letter`` or ``a4`` — feeds CSS ``@page size``. */
  pageSize: "letter" | "a4";
  /** Top/bottom and left/right page margins as CSS lengths. */
  pageMarginV: string;
  pageMarginH: string;
  cols: number;
  rows: number;
  labelWidth: string;
  labelHeight: string;
  columnGap: string;
  rowGap: string;
  /** Total grid width (= cols × labelWidth + (cols-1) × columnGap). */
  sheetContentWidth: string;
}

export const LABEL_TEMPLATES: readonly LabelTemplate[] = [
  {
    id: "avery_5160",
    name: "Avery 5160 / 5260 / 8160 — 1″ × 2⅝″ (30/sheet, Letter)",
    pageSize: "letter",
    pageMarginV: "0.5in",
    pageMarginH: "0.1875in",
    cols: 3,
    rows: 10,
    labelWidth: "2.625in",
    labelHeight: "1in",
    columnGap: "0.125in",
    rowGap: "0",
    sheetContentWidth: "8.125in", // 3×2.625 + 2×0.125
  },
  {
    id: "avery_5161",
    name: "Avery 5161 — 1″ × 4″ (20/sheet, Letter)",
    pageSize: "letter",
    pageMarginV: "0.5in",
    pageMarginH: "0.15625in",
    cols: 2,
    rows: 10,
    labelWidth: "4in",
    labelHeight: "1in",
    columnGap: "0.1875in",
    rowGap: "0",
    sheetContentWidth: "8.1875in",
  },
  {
    id: "avery_5163",
    name: "Avery 5163 — 2″ × 4″ (10/sheet, Letter)",
    pageSize: "letter",
    pageMarginV: "0.5in",
    pageMarginH: "0.15625in",
    cols: 2,
    rows: 5,
    labelWidth: "4in",
    labelHeight: "2in",
    columnGap: "0.1875in",
    rowGap: "0",
    sheetContentWidth: "8.1875in",
  },
  {
    id: "avery_5167",
    name: "Avery 5167 — ½″ × 1¾″ (80/sheet, Letter)",
    pageSize: "letter",
    pageMarginV: "0.5in",
    pageMarginH: "0.28125in",
    cols: 4,
    rows: 20,
    labelWidth: "1.75in",
    labelHeight: "0.5in",
    columnGap: "0.3125in",
    rowGap: "0",
    sheetContentWidth: "7.9375in",
  },
  {
    id: "avery_5264",
    name: "Avery 5264 — 3⅓″ × 4″ (6/sheet, Letter)",
    pageSize: "letter",
    pageMarginV: "0.5in",
    pageMarginH: "0.15625in",
    cols: 2,
    rows: 3,
    labelWidth: "4in",
    labelHeight: "3.333in",
    columnGap: "0.1875in",
    rowGap: "0",
    sheetContentWidth: "8.1875in",
  },
];

export const DEFAULT_LABEL_TEMPLATE: LabelTemplate = LABEL_TEMPLATES[0]!;

export function findTemplate(id: string | null | undefined): LabelTemplate {
  if (!id) return DEFAULT_LABEL_TEMPLATE;
  return (
    LABEL_TEMPLATES.find((t) => t.id === id) ?? DEFAULT_LABEL_TEMPLATE
  );
}

let cachedId: string | null = null;
let inFlight: Promise<string> | null = null;

async function fetchTemplateId(): Promise<string> {
  if (cachedId !== null) return cachedId;
  if (inFlight !== null) return inFlight;
  inFlight = apiClient
    .get<{ value: string }>(
      `/api/v1/settings/${encodeURIComponent(SETTING_KEY)}`,
    )
    .then((res) => {
      const id =
        typeof res.data.value === "string"
          ? res.data.value
          : DEFAULT_LABEL_TEMPLATE.id;
      cachedId = id;
      return id;
    })
    .catch(() => {
      cachedId = DEFAULT_LABEL_TEMPLATE.id;
      return DEFAULT_LABEL_TEMPLATE.id;
    })
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

/** Subscribe to the configured label template. Returns the registry
 * default until the settings fetch lands. */
export function useLabelTemplate(): LabelTemplate {
  const [template, setTemplate] = useState<LabelTemplate>(
    findTemplate(cachedId),
  );
  useEffect(() => {
    let cancelled = false;
    fetchTemplateId().then((id) => {
      if (!cancelled) setTemplate(findTemplate(id));
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return template;
}

export function invalidateLabelTemplateCache(): void {
  cachedId = null;
}
