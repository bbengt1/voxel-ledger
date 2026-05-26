/**
 * Reconcile (physical-count) modal.
 *
 * Operator picks a location, sees the current on-hand for that location,
 * enters the actual counted quantity, and submits. The component
 * computes ``delta = counted - on_hand`` and POSTs an ``adjustment``
 * transaction with the signed delta — never the raw counted figure —
 * so the inventory ledger stays append-only and auditable.
 */
import { useEffect, useMemo, useState } from "react";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";

type InventoryLocationResponse =
  components["schemas"]["InventoryLocationResponse"];
type InventoryTransactionResponse =
  components["schemas"]["InventoryTransactionResponse"];

export type ReconcileEntityKind = "material" | "supply" | "product";

interface Props {
  open: boolean;
  onClose: () => void;
  onReconciled: (summary: string) => void;
  entity: {
    id: string;
    kind: ReconcileEntityKind;
    label: string;
  };
  unit: string;
  /** Current per-location balances (location_id → quantity as string). */
  perLocationOnHand: Record<string, string> | null | undefined;
}

function asNumber(value: string | undefined): number {
  if (!value) return 0;
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

export function ReconcileModal({
  open,
  onClose,
  onReconciled,
  entity,
  unit,
  perLocationOnHand,
}: Props) {
  const [locations, setLocations] = useState<InventoryLocationResponse[]>([]);
  const [locationId, setLocationId] = useState<string>("");
  const [counted, setCounted] = useState<string>("");
  const [reason, setReason] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
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
  }, [open]);

  useEffect(() => {
    if (!open) {
      setCounted("");
      setReason("");
      setError(null);
      setLocationId("");
    }
  }, [open]);

  const currentOnHand = useMemo(() => {
    if (!locationId) return "0";
    return perLocationOnHand?.[locationId] ?? "0";
  }, [locationId, perLocationOnHand]);

  const delta = useMemo(() => {
    if (!locationId || counted === "") return null;
    const c = Number(counted);
    if (!Number.isFinite(c)) return null;
    return c - asNumber(currentOnHand);
  }, [counted, currentOnHand, locationId]);

  async function submit() {
    if (!locationId) {
      setError("Pick a location.");
      return;
    }
    if (counted === "" || !Number.isFinite(Number(counted))) {
      setError("Enter the counted quantity.");
      return;
    }
    const computedDelta = Number(counted) - asNumber(currentOnHand);
    if (computedDelta === 0) {
      setError("Counted matches current on-hand — nothing to reconcile.");
      return;
    }
    setSubmitting(true);
    setError(null);
    const locationName =
      locations.find((l) => l.id === locationId)?.name ?? locationId;
    const body = {
      kind: "adjustment" as const,
      entity_kind: entity.kind,
      entity_id: entity.id,
      location_id: locationId,
      quantity: computedDelta.toString(),
      reason:
        reason.trim() ||
        `Reconcile @ ${locationName}: counted ${counted} ${unit}, was ${currentOnHand} ${unit}`,
    };
    try {
      await apiClient.post<InventoryTransactionResponse>(
        "/api/v1/inventory/transactions",
        body,
      );
      const sign = computedDelta > 0 ? "+" : "";
      onReconciled(
        `Reconciled ${entity.label} @ ${locationName} (${sign}${computedDelta} ${unit}).`,
      );
      onClose();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not reconcile.";
      setError(typeof detail === "string" ? detail : "Could not reconcile.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => (!o ? onClose() : undefined)}>
      <DialogContent>
        <DialogTitle>Reconcile {entity.label}</DialogTitle>
        <DialogDescription>
          Pick a location, enter the actual counted quantity, and submit. An
          adjustment for the difference will be posted automatically.
        </DialogDescription>

        <div className="mt-4 space-y-3">
          <label className="block text-sm">
            Location
            <select
              className="mt-1 block w-full rounded border border-input bg-background px-2 py-1 text-sm"
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
              disabled={submitting}
              data-testid="reconcile-location"
            >
              <option value="">Select a location…</option>
              {locations.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>

          {locationId ? (
            <div className="rounded border border-border bg-muted/40 p-3 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Current on-hand</span>
                <span
                  className="tabular-nums"
                  data-testid="reconcile-current"
                >
                  {currentOnHand} {unit}
                </span>
              </div>
              {delta !== null ? (
                <div className="mt-1 flex justify-between">
                  <span className="text-muted-foreground">Adjustment</span>
                  <span
                    className={
                      "tabular-nums " +
                      (delta > 0
                        ? "text-green-600"
                        : delta < 0
                          ? "text-destructive"
                          : "")
                    }
                    data-testid="reconcile-delta"
                  >
                    {delta > 0 ? "+" : ""}
                    {delta} {unit}
                  </span>
                </div>
              ) : null}
            </div>
          ) : null}

          <label className="block text-sm">
            Counted ({unit})
            <Input
              className="mt-1"
              inputMode="decimal"
              value={counted}
              onChange={(e) => setCounted(e.target.value)}
              disabled={submitting || !locationId}
              data-testid="reconcile-counted"
            />
          </label>

          <label className="block text-sm">
            Reason (optional)
            <Input
              className="mt-1"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              disabled={submitting}
              placeholder="Quarterly stocktake, spill, etc."
              data-testid="reconcile-reason"
            />
          </label>

          {error ? (
            <p
              role="alert"
              className="text-sm text-destructive"
              data-testid="reconcile-error"
            >
              {error}
            </p>
          ) : null}

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={submit}
              disabled={submitting}
              data-testid="reconcile-submit"
            >
              {submitting ? "Saving…" : "Reconcile"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
