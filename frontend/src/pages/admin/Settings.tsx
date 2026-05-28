import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  LABEL_TEMPLATES,
  invalidateLabelTemplateCache,
} from "@/lib/labelTemplates";
import { invalidateMaterialTypesCache } from "@/lib/materialTypes";
import { invalidatePlacesOfPurchaseCache } from "@/lib/placesOfPurchase";

interface SettingRow {
  key: string;
  value: unknown;
  default: unknown;
  schema_type: string;
  updated_at: string | null;
  updated_by_user_id: string | null;
}

interface SettingDef {
  key: string;
  label: string;
  help: string;
  // Renders as a plain text input; "number" hint is just for inputMode.
  // ``string-list`` renders a multi-line textarea where each non-blank
  // line is one entry.
  kind:
    | "string"
    | "decimal"
    | "percent"
    | "currency-code"
    | "string-list"
    | "label-template";
}

// Only the operator-tunable knobs. Excludes infra (storage paths,
// account-id pointers, reference-padding widths) — those belong in
// admin tooling, not a daily-driver settings page.
const EDITABLE_SETTINGS: SettingDef[] = [
  {
    key: "display.currency",
    label: "Display currency",
    help: "ISO 4217 code (USD, EUR, GBP, …). Controls how money is rendered in the UI.",
    kind: "currency-code",
  },
  {
    key: "materials.types",
    label: "Material types",
    help: "Filament types shown in the material picker. One per line. Custom values are still accepted when entering a material.",
    kind: "string-list",
  },
  {
    key: "supplies.places_of_purchase",
    label: "Supplies — places of purchase",
    help: "Suggested storefronts in the supply place-of-purchase picker. One per line. Custom values still accepted.",
    kind: "string-list",
  },
  {
    key: "labels.template",
    label: "Product label template",
    help: "Avery-style sheet used by the Catalog → Labels print page. Pick the stock you keep in the printer; the grid resizes to match.",
    kind: "label-template",
  },
  {
    key: "cost_engine.labor_rate_per_hour",
    label: "Labor rate ($/hour) — fallback",
    help: "Fallback hourly labor cost. Overridden by any Rate row marked “default for kind” in the Rate catalog — manage labor rates there for history and named rates.",
    kind: "decimal",
  },
  {
    key: "cost_engine.machine_rate_per_hour",
    label: "Machine rate ($/hour) — fallback",
    help: "Fallback flat per-hour machine cost when a printer has no per-printer cost params. Overridden by any default Rate row in the Rate catalog (and by per-printer Rate overrides).",
    kind: "decimal",
  },
  {
    key: "cost_engine.overhead_percent",
    label: "Overhead (%) — fallback",
    help: "Fallback surcharge applied to direct costs. Overridden by any default overhead Rate row in the Rate catalog.",
    kind: "percent",
  },
  {
    key: "cost_engine.power_cost_per_kwh",
    label: "Electricity rate ($/kWh)",
    help: "Used with per-printer wattage to derive electricity cost.",
    kind: "decimal",
  },
  {
    key: "cost_engine.default_margin_percent",
    label: "Default margin (%)",
    help: "Default markup applied to suggested unit prices.",
    kind: "percent",
  },
  {
    key: "cost_engine.failure_rate_percent",
    label: "Failure rate buffer (%)",
    help: "Multiplies direct costs to absorb the expected fraction of failed prints.",
    kind: "percent",
  },
];

function asString(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "string") return v;
  return String(v);
}

function toDraft(v: unknown, kind: SettingDef["kind"]): string {
  if (kind === "string-list") {
    if (Array.isArray(v)) return v.map((s) => String(s)).join("\n");
    return "";
  }
  return asString(v);
}

function fromDraft(draft: string, kind: SettingDef["kind"]): unknown {
  if (kind === "string-list") {
    return draft
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
  }
  if (kind === "currency-code") return draft.trim().toUpperCase();
  return draft.trim();
}

export function SettingsPage() {
  const [records, setRecords] = useState<Record<string, SettingRow>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    apiClient
      .get<SettingRow[]>("/api/v1/settings")
      .then((res) => {
        const map: Record<string, SettingRow> = {};
        const next: Record<string, string> = {};
        const defByKey = new Map(EDITABLE_SETTINGS.map((d) => [d.key, d]));
        for (const row of res.data) {
          const def = defByKey.get(row.key);
          if (!def) continue;
          map[row.key] = row;
          next[row.key] = toDraft(row.value ?? row.default, def.kind);
        }
        setRecords(map);
        setDrafts(next);
      })
      .catch(() => {
        setError(
          "Could not load settings. You need the owner or bookkeeper role.",
        );
      })
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function save(def: SettingDef) {
    setSavingKey(def.key);
    setSavedMsg(null);
    setError(null);
    const value = fromDraft(drafts[def.key] ?? "", def.kind);
    try {
      const res = await apiClient.put<SettingRow>(
        `/api/v1/settings/${encodeURIComponent(def.key)}`,
        { value },
      );
      setRecords((prev) => ({ ...prev, [def.key]: res.data }));
      setDrafts((prev) => ({
        ...prev,
        [def.key]: toDraft(res.data.value ?? res.data.default, def.kind),
      }));
      setSavedMsg(`Saved ${def.label}.`);
      if (def.key === "materials.types") invalidateMaterialTypesCache();
      if (def.key === "supplies.places_of_purchase")
        invalidatePlacesOfPurchaseCache();
      if (def.key === "labels.template") invalidateLabelTemplateCache();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? `Could not save ${def.label}.`;
      setError(typeof detail === "string" ? detail : `Could not save ${def.label}.`);
    } finally {
      setSavingKey(null);
    }
  }

  return (
    <section className="max-w-2xl">
      <h1 className="text-xl font-semibold">Settings</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Operator-tunable knobs. Saving each row is independent. Writes require
        the owner role.
      </p>
      <p
        className="mt-3 rounded border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
        data-testid="settings-rate-fallback-note"
      >
        Labor, machine, and overhead values here are{" "}
        <span className="font-medium">fallbacks</span>. If you have a Rate row
        marked “default for kind” in the Rate catalog, that wins. Use the
        Rate catalog for named rates, history, and per-printer machine
        overrides.
      </p>

      {loading ? (
        <p className="mt-6 text-sm text-muted-foreground">Loading…</p>
      ) : null}

      {error ? (
        <p role="alert" className="mt-4 text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {savedMsg ? (
        <p role="status" className="mt-4 text-sm text-green-600">
          {savedMsg}
        </p>
      ) : null}

      {!loading && !error ? (
        <ul className="mt-6 space-y-5" data-testid="settings-list">
          {EDITABLE_SETTINGS.map((def) => {
            const record = records[def.key];
            const draft = drafts[def.key] ?? "";
            return (
              <li
                key={def.key}
                className="rounded border border-border bg-card p-4"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <label
                      htmlFor={`setting-${def.key}`}
                      className="block text-sm font-medium"
                    >
                      {def.label}
                    </label>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {def.help}
                    </p>
                    {def.kind === "string-list" ? (
                      <div className="mt-2 space-y-2">
                        <textarea
                          id={`setting-${def.key}`}
                          value={draft}
                          rows={Math.max(6, draft.split("\n").length + 1)}
                          onChange={(e) =>
                            setDrafts((prev) => ({
                              ...prev,
                              [def.key]: e.target.value,
                            }))
                          }
                          className="block w-full rounded border border-input bg-background px-2 py-1 font-mono text-sm"
                          data-testid={`setting-input-${def.key}`}
                        />
                        <Button
                          type="button"
                          onClick={() => save(def)}
                          disabled={savingKey === def.key}
                          data-testid={`setting-save-${def.key}`}
                        >
                          {savingKey === def.key ? "Saving…" : "Save"}
                        </Button>
                      </div>
                    ) : def.kind === "label-template" ? (
                      <div className="mt-2 flex items-center gap-2">
                        <select
                          id={`setting-${def.key}`}
                          value={draft}
                          onChange={(e) =>
                            setDrafts((prev) => ({
                              ...prev,
                              [def.key]: e.target.value,
                            }))
                          }
                          className="block w-full rounded border border-input bg-background px-2 py-1 text-sm"
                          data-testid={`setting-input-${def.key}`}
                        >
                          {LABEL_TEMPLATES.map((t) => (
                            <option key={t.id} value={t.id}>
                              {t.name}
                            </option>
                          ))}
                        </select>
                        <Button
                          type="button"
                          onClick={() => save(def)}
                          disabled={savingKey === def.key}
                          data-testid={`setting-save-${def.key}`}
                        >
                          {savingKey === def.key ? "Saving…" : "Save"}
                        </Button>
                      </div>
                    ) : (
                      <div className="mt-2 flex items-center gap-2">
                        <Input
                          id={`setting-${def.key}`}
                          value={draft}
                          inputMode={
                            def.kind === "currency-code" ? "text" : "decimal"
                          }
                          maxLength={def.kind === "currency-code" ? 3 : undefined}
                          onChange={(e) =>
                            setDrafts((prev) => ({
                              ...prev,
                              [def.key]: e.target.value,
                            }))
                          }
                          data-testid={`setting-input-${def.key}`}
                        />
                        <Button
                          type="button"
                          onClick={() => save(def)}
                          disabled={savingKey === def.key}
                          data-testid={`setting-save-${def.key}`}
                        >
                          {savingKey === def.key ? "Saving…" : "Save"}
                        </Button>
                      </div>
                    )}
                    {record ? (
                      <p className="mt-2 text-xs text-muted-foreground">
                        Default{" "}
                        {def.kind === "string-list" &&
                        Array.isArray(record.default)
                          ? `${(record.default as unknown[]).length} entries`
                          : asString(record.default)}{" "}
                        ·{" "}
                        {record.updated_at
                          ? `last changed ${new Date(record.updated_at).toLocaleString()}`
                          : "never changed"}
                      </p>
                    ) : null}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
