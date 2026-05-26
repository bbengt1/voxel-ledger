/**
 * Inline "On hand" section for material / supply / product detail pages.
 *
 * Headline = total across all locations (sourced from the entity
 * response's ``total_on_hand``). Below that, a per-location breakdown
 * table, then role-aware action buttons that open the inventory modals
 * pre-filled for this entity. An inline "Set threshold" editor lets
 * owner + production tweak the low-stock threshold without leaving the
 * page.
 */
import { useEffect, useMemo, useState } from "react";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { ReconcileModal } from "@/components/inventory/ReconcileModal";
import { RecordTransactionModal } from "@/components/inventory/RecordTransactionModal";
import { TransferStockModal } from "@/components/inventory/TransferStockModal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type InventoryLocationResponse =
  components["schemas"]["InventoryLocationResponse"];

export type OnHandEntityKind = "material" | "supply" | "product";

interface Props {
  entityKind: OnHandEntityKind;
  entityId: string;
  entityName: string;
  totalOnHand: string;
  perLocationOnHand?: Record<string, string> | null;
  unit: string;
  lowStockThreshold: string | null;
  /** Called after a transaction is recorded so the parent can refetch. */
  onChanged?: () => void;
}

const WRITE_ROLES = new Set(["owner", "production"]);

function thresholdFieldFor(kind: OnHandEntityKind): string {
  if (kind === "material") return "low_stock_threshold_grams";
  return "low_stock_threshold";
}

function patchPathFor(kind: OnHandEntityKind, id: string): string {
  if (kind === "material") return `/api/v1/materials/${id}`;
  if (kind === "supply") return `/api/v1/supplies/${id}`;
  return `/api/v1/products/${id}`;
}

export function OnHandSection({
  entityKind,
  entityId,
  entityName,
  totalOnHand,
  perLocationOnHand,
  unit,
  lowStockThreshold,
  onChanged,
}: Props) {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = !!role && WRITE_ROLES.has(role);
  const canTransfer = canWrite && entityKind !== "supply";

  const [locations, setLocations] = useState<InventoryLocationResponse[]>([]);
  const [recordOpen, setRecordOpen] = useState(false);
  const [recordKind, setRecordKind] = useState<"receipt" | "adjustment">(
    "receipt",
  );
  const [transferOpen, setTransferOpen] = useState(false);
  const [reconcileOpen, setReconcileOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [editingThreshold, setEditingThreshold] = useState(false);
  const [thresholdInput, setThresholdInput] = useState(lowStockThreshold ?? "");
  const [savingThreshold, setSavingThreshold] = useState(false);
  const [thresholdError, setThresholdError] = useState<string | null>(null);

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

  const locationNameById = useMemo(() => {
    const m = new Map<string, string>();
    for (const loc of locations) m.set(loc.id, loc.name);
    return m;
  }, [locations]);

  const rows = useMemo(() => {
    const entries = Object.entries(perLocationOnHand ?? {});
    return entries
      .map(([locId, qty]) => ({
        id: locId,
        name: locationNameById.get(locId) ?? locId.slice(0, 8) + "…",
        qty,
      }))
      .sort((a, b) => Number(b.qty) - Number(a.qty));
  }, [perLocationOnHand, locationNameById]);

  function openRecord(kind: "receipt" | "adjustment") {
    setRecordKind(kind);
    setRecordOpen(true);
  }

  async function saveThreshold() {
    setSavingThreshold(true);
    setThresholdError(null);
    try {
      const field = thresholdFieldFor(entityKind);
      const body: Record<string, unknown> = {
        [field]: thresholdInput.trim() || null,
      };
      await apiClient.patch(patchPathFor(entityKind, entityId), body);
      setEditingThreshold(false);
      onChanged?.();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not save threshold.";
      setThresholdError(
        typeof detail === "string" ? detail : "Could not save threshold.",
      );
    } finally {
      setSavingThreshold(false);
    }
  }

  return (
    <section
      className="space-y-3 border-t border-border pt-4"
      data-testid="on-hand-section"
    >
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">On hand</h2>
          <p className="text-2xl font-semibold" data-testid="on-hand-total">
            {totalOnHand} {unit}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canWrite ? (
            <>
              <Button
                size="sm"
                onClick={() => openRecord("receipt")}
                data-testid="onhand-record-receipt"
              >
                Record receipt
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => openRecord("adjustment")}
                data-testid="onhand-record-adjustment"
              >
                Record adjustment
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setReconcileOpen(true)}
                data-testid="onhand-reconcile"
              >
                Reconcile
              </Button>
            </>
          ) : null}
          {canTransfer ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setTransferOpen(true)}
              data-testid="onhand-transfer"
            >
              Transfer
            </Button>
          ) : null}
        </div>
      </header>

      {toast ? (
        <p
          role="status"
          className="text-xs text-muted-foreground"
          data-testid="onhand-toast"
        >
          {toast}
        </p>
      ) : null}

      {rows.length > 0 ? (
        <table
          className="w-full table-fixed border-collapse text-sm"
          data-testid="onhand-per-location"
        >
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
              <th className="py-2 pr-2">Location</th>
              <th className="py-2 pr-2 text-right">Quantity</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-border/50">
                <td className="py-1 pr-2">{r.name}</td>
                <td className="py-1 pr-2 text-right tabular-nums">
                  {r.qty} {unit}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-xs text-muted-foreground">
          No per-location balances yet.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground">Low-stock threshold:</span>
        {editingThreshold ? (
          <>
            <Input
              className="h-8 w-32"
              inputMode="decimal"
              value={thresholdInput}
              onChange={(e) => setThresholdInput(e.target.value)}
              disabled={savingThreshold}
              data-testid="threshold-input"
            />
            <Button
              size="sm"
              onClick={saveThreshold}
              disabled={savingThreshold}
              data-testid="threshold-save"
            >
              {savingThreshold ? "Saving…" : "Save"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setEditingThreshold(false);
                setThresholdInput(lowStockThreshold ?? "");
                setThresholdError(null);
              }}
              disabled={savingThreshold}
            >
              Cancel
            </Button>
            {thresholdError ? (
              <span
                role="alert"
                className="text-xs text-destructive"
                data-testid="threshold-error"
              >
                {thresholdError}
              </span>
            ) : null}
          </>
        ) : (
          <>
            <span data-testid="threshold-value">
              {lowStockThreshold ?? "—"}
            </span>
            {canWrite ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setThresholdInput(lowStockThreshold ?? "");
                  setEditingThreshold(true);
                }}
                data-testid="threshold-edit"
              >
                Edit
              </Button>
            ) : null}
          </>
        )}
      </div>

      <RecordTransactionModal
        open={recordOpen}
        onClose={() => setRecordOpen(false)}
        onRecorded={(_tx, summary) => {
          setToast(summary);
          onChanged?.();
        }}
        role={role}
        initialKind={recordKind}
        fixedEntity={{
          id: entityId,
          label: entityName,
          kind: entityKind,
        }}
      />

      <ReconcileModal
        open={reconcileOpen}
        onClose={() => setReconcileOpen(false)}
        onReconciled={(summary) => {
          setToast(summary);
          onChanged?.();
        }}
        entity={{ id: entityId, kind: entityKind, label: entityName }}
        unit={unit}
        perLocationOnHand={perLocationOnHand}
      />

      <TransferStockModal
        open={transferOpen}
        onClose={() => setTransferOpen(false)}
        onTransferred={() => {
          setToast(`Transferred ${entityName}`);
          onChanged?.();
        }}
        fixedEntity={{
          id: entityId,
          label: entityName,
          kind: entityKind,
        }}
      />
    </section>
  );
}
