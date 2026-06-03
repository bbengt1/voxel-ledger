/**
 * Starting balances entry page.
 *
 * Two modes:
 *   - Single: pick entity + location, enter qty, post one ``adjustment``
 *     with ``reason="initial balance"``.
 *   - Bulk: tabular input; each row is walked serially with a progress
 *     indicator. Row failures stay in the table with an inline error and
 *     don't block subsequent rows.
 *
 * Backend gates the underlying endpoint to owner + production; the
 * route is also role-gated upstream.
 */
import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import {
  EntityPicker,
  type EntityKind,
  type EntityOption,
} from "@/components/inventory/EntityPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type InventoryLocationResponse =
  components["schemas"]["InventoryLocationResponse"];

const ALLOWED_ROLES = new Set(["owner", "production"]);

interface BulkRow {
  id: number;
  entityKind: EntityKind;
  entity: EntityOption | null;
  locationId: string;
  quantity: string;
  status: "pending" | "ok" | "error";
  error: string | null;
}

let _rowSeq = 0;
function makeRow(): BulkRow {
  return {
    id: ++_rowSeq,
    entityKind: "material",
    entity: null,
    locationId: "",
    quantity: "",
    status: "pending",
    error: null,
  };
}

export function StartingBalancesPage() {
  const role = useAuthStore((s) => s.user?.role);
  if (!role || !ALLOWED_ROLES.has(role)) {
    return <Navigate to="/" replace />;
  }

  return <StartingBalancesInner />;
}

function StartingBalancesInner() {
  const [mode, setMode] = useState<"single" | "bulk">("single");
  const [locations, setLocations] = useState<InventoryLocationResponse[]>([]);

  // Single mode
  const [entityKind, setEntityKind] = useState<EntityKind>("material");
  const [entity, setEntity] = useState<EntityOption | null>(null);
  const [locationId, setLocationId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [singleMsg, setSingleMsg] = useState<string | null>(null);
  const [singleErr, setSingleErr] = useState<string | null>(null);

  // Bulk mode
  const [rows, setRows] = useState<BulkRow[]>(() => [makeRow()]);
  const [bulkRunning, setBulkRunning] = useState(false);
  const [bulkProgress, setBulkProgress] = useState({ done: 0, total: 0 });
  const [bulkSummary, setBulkSummary] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<{ items: InventoryLocationResponse[] }>(
        "/api/v1/inventory/locations",
        { params: { is_archived: "false" } },
      )
      .then((res) => {
        if (cancelled) return;
        setLocations(res.data.items);
      })
      .catch(() => {
        if (!cancelled) setLocations([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function submitSingle(e: React.FormEvent) {
    e.preventDefault();
    setSingleMsg(null);
    setSingleErr(null);
    if (!entity) {
      setSingleErr("Pick an entity.");
      return;
    }
    if (!locationId) {
      setSingleErr("Pick a location.");
      return;
    }
    if (!quantity.trim()) {
      setSingleErr("Quantity is required.");
      return;
    }
    setSubmitting(true);
    try {
      await apiClient.post("/api/v1/inventory/transactions", {
        kind: "adjustment",
        entity_kind: entityKind,
        entity_id: entity.id,
        location_id: locationId,
        quantity: quantity.trim(),
        reason: "initial balance",
      });
      setSingleMsg(`Recorded initial balance for ${entity.label}.`);
      setQuantity("");
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not record balance.";
      setSingleErr(
        typeof detail === "string" ? detail : "Could not record balance.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  function updateRow(id: number, patch: Partial<BulkRow>) {
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }

  function addRow() {
    setRows((rs) => [...rs, makeRow()]);
  }

  function removeRow(id: number) {
    setRows((rs) => rs.filter((r) => r.id !== id));
  }

  async function runBulk() {
    const pending = rows.filter((r) => r.status !== "ok");
    setBulkRunning(true);
    setBulkSummary(null);
    setBulkProgress({ done: 0, total: pending.length });
    let ok = 0;
    let failed = 0;
    for (const r of pending) {
      if (!r.entity || !r.locationId || !r.quantity.trim()) {
        updateRow(r.id, {
          status: "error",
          error: "Missing entity, location, or quantity.",
        });
        failed++;
        setBulkProgress((p) => ({ ...p, done: p.done + 1 }));
        continue;
      }
      try {
        await apiClient.post("/api/v1/inventory/transactions", {
          kind: "adjustment",
          entity_kind: r.entityKind,
          entity_id: r.entity.id,
          location_id: r.locationId,
          quantity: r.quantity.trim(),
          reason: "initial balance",
        });
        updateRow(r.id, { status: "ok", error: null });
        ok++;
      } catch (err: unknown) {
        const detail =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed.";
        updateRow(r.id, {
          status: "error",
          error: typeof detail === "string" ? detail : "Failed.",
        });
        failed++;
      }
      setBulkProgress((p) => ({ ...p, done: p.done + 1 }));
    }
    setBulkSummary(
      `${ok} of ${pending.length} recorded, ${failed} failed.`,
    );
    setBulkRunning(false);
  }

  return (
    <section className="flex flex-col gap-4">
      <header>
        <h1 className="text-xl font-semibold">Starting balances</h1>
        <p className="text-sm text-muted-foreground">
          Records adjustment transactions tagged{" "}
          <code>reason=&quot;initial balance&quot;</code> for one or many
          entity/location pairs.
        </p>
      </header>

      <div className="flex gap-2">
        <Button
          variant={mode === "single" ? "default" : "outline"}
          onClick={() => setMode("single")}
          data-testid="mode-single"
        >
          Single entry
        </Button>
        <Button
          variant={mode === "bulk" ? "default" : "outline"}
          onClick={() => setMode("bulk")}
          data-testid="mode-bulk"
        >
          Bulk entry
        </Button>
      </div>

      {mode === "single" ? (
        <form
          className="max-w-md space-y-3 rounded-md border border-border p-4"
          onSubmit={submitSingle}
          data-testid="single-form"
        >
          <label className="block text-sm">
            Entity kind
            <select
              className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              value={entityKind}
              onChange={(e) => {
                setEntityKind(e.target.value as EntityKind);
                setEntity(null);
              }}
            >
              <option value="material">Material</option>
              <option value="supply">Supply</option>
              <option value="product">Product</option>
            </select>
          </label>
          <label className="block text-sm">
            Entity
            <div className="mt-1">
              <EntityPicker
                kind={entityKind}
                value={entity}
                onChange={setEntity}
                data-testid="single-entity"
              />
            </div>
          </label>
          <label className="block text-sm">
            Location
            <select
              className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
              data-testid="single-location"
            >
              <option value="">Pick a location…</option>
              {locations.map((loc) => (
                <option key={loc.id} value={loc.id}>
                  {loc.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            Quantity
            <Input
              className="mt-1"
              inputMode="decimal"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              data-testid="single-quantity"
              required
            />
          </label>
          {singleErr ? (
            <p
              role="alert"
              className="text-sm text-destructive"
              data-testid="single-err"
            >
              {singleErr}
            </p>
          ) : null}
          {singleMsg ? (
            <p
              role="status"
              className="text-sm text-emerald-600 dark:text-emerald-400"
              data-testid="single-msg"
            >
              {singleMsg}
            </p>
          ) : null}
          <Button type="submit" disabled={submitting} data-testid="single-submit">
            {submitting ? "Recording…" : "Record"}
          </Button>
        </form>
      ) : (
        <div className="space-y-3">
          <div className="overflow-x-auto">
          <table
            className="w-full min-w-[44rem] border-collapse text-sm"
            data-testid="bulk-table"
          >
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                <th className="py-2 pr-2">Kind</th>
                <th className="py-2 pr-2">Entity</th>
                <th className="py-2 pr-2">Location</th>
                <th className="py-2 pr-2">Quantity</th>
                <th className="py-2 pr-2">Status</th>
                <th className="py-2 pr-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.id}
                  className="border-b border-border/50 align-top"
                  data-testid={`bulk-row-${r.id}`}
                >
                  <td className="py-1 pr-2">
                    <select
                      className="h-8 rounded-md border border-input bg-background px-2 text-sm"
                      value={r.entityKind}
                      onChange={(e) =>
                        updateRow(r.id, {
                          entityKind: e.target.value as EntityKind,
                          entity: null,
                        })
                      }
                      disabled={bulkRunning || r.status === "ok"}
                    >
                      <option value="material">Material</option>
                      <option value="supply">Supply</option>
                      <option value="product">Product</option>
                    </select>
                  </td>
                  <td className="py-1 pr-2 w-56">
                    <EntityPicker
                      kind={r.entityKind}
                      value={r.entity}
                      onChange={(opt) => updateRow(r.id, { entity: opt })}
                      disabled={bulkRunning || r.status === "ok"}
                    />
                  </td>
                  <td className="py-1 pr-2">
                    <select
                      className="h-8 rounded-md border border-input bg-background px-2 text-sm"
                      value={r.locationId}
                      onChange={(e) =>
                        updateRow(r.id, { locationId: e.target.value })
                      }
                      disabled={bulkRunning || r.status === "ok"}
                    >
                      <option value="">Pick…</option>
                      {locations.map((loc) => (
                        <option key={loc.id} value={loc.id}>
                          {loc.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="py-1 pr-2">
                    <Input
                      className="h-8 w-24"
                      inputMode="decimal"
                      value={r.quantity}
                      onChange={(e) =>
                        updateRow(r.id, { quantity: e.target.value })
                      }
                      disabled={bulkRunning || r.status === "ok"}
                    />
                  </td>
                  <td className="py-1 pr-2 text-xs">
                    {r.status === "ok" ? (
                      <span className="text-emerald-600 dark:text-emerald-400">
                        OK
                      </span>
                    ) : r.status === "error" ? (
                      <span
                        className="text-destructive"
                        data-testid={`bulk-row-error-${r.id}`}
                      >
                        {r.error}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">Pending</span>
                    )}
                  </td>
                  <td className="py-1 pr-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => removeRow(r.id)}
                      disabled={bulkRunning}
                    >
                      Remove
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="outline" onClick={addRow} disabled={bulkRunning}>
              Add row
            </Button>
            <Button
              onClick={runBulk}
              disabled={bulkRunning || rows.length === 0}
              data-testid="bulk-submit"
            >
              {bulkRunning
                ? `Recording ${bulkProgress.done}/${bulkProgress.total}…`
                : "Record all"}
            </Button>
            {bulkSummary ? (
              <span
                role="status"
                data-testid="bulk-summary"
                className="text-sm"
              >
                {bulkSummary}
              </span>
            ) : null}
          </div>
        </div>
      )}
    </section>
  );
}
