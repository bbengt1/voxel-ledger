/**
 * Modal to POST an inventory transaction.
 *
 * Filters available kinds by the caller's role per the backend matrix:
 *   - sales: only ``sale_out``.
 *   - owner / production: every kind except ``transfer_in`` / ``transfer_out``
 *     (which are produced by the transfer endpoint, not this one).
 *   - bookkeeper / viewer: nothing — the parent should hide the trigger.
 *
 * Doherty: submit button shows an inline spinner and the form is disabled
 * during the in-flight request so users get acknowledgement well under
 * 400ms.
 */
import { useEffect, useMemo, useState } from "react";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import {
  EntityPicker,
  type EntityKind,
  type EntityOption,
} from "@/components/inventory/EntityPicker";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import type { Role } from "@/store/useAuthStore";

type InventoryTransactionCreate =
  components["schemas"]["InventoryTransactionCreate"];
type InventoryTransactionResponse =
  components["schemas"]["InventoryTransactionResponse"];
type InventoryLocationResponse =
  components["schemas"]["InventoryLocationResponse"];

export type TransactionKind = InventoryTransactionCreate["kind"];

const ALL_KINDS: ReadonlyArray<{ value: TransactionKind; label: string }> = [
  { value: "production_in", label: "Production in" },
  { value: "sale_out", label: "Sale out" },
  { value: "adjustment", label: "Adjustment" },
  { value: "return_in", label: "Return in" },
  { value: "waste", label: "Waste" },
  { value: "receipt", label: "Receipt" },
];

const SALES_KINDS: ReadonlySet<TransactionKind> = new Set(["sale_out"]);
const PRODUCTION_KINDS: ReadonlySet<TransactionKind> = new Set([
  "production_in",
  "adjustment",
  "return_in",
  "waste",
  "receipt",
]);

function kindsForRole(role: Role | undefined): TransactionKind[] {
  if (role === "owner") return ALL_KINDS.map((k) => k.value);
  if (role === "production")
    return ALL_KINDS.filter((k) => PRODUCTION_KINDS.has(k.value)).map(
      (k) => k.value,
    );
  if (role === "sales")
    return ALL_KINDS.filter((k) => SALES_KINDS.has(k.value)).map(
      (k) => k.value,
    );
  return [];
}

interface Props {
  open: boolean;
  onClose: () => void;
  onRecorded: (
    tx: InventoryTransactionResponse,
    summary: string,
  ) => void;
  role: Role | undefined;
  /** Prefill — entity kind. */
  initialEntityKind?: EntityKind;
  /** Prefill — entity. Forces a fixed entity (picker hidden) if set. */
  fixedEntity?: EntityOption & { kind: EntityKind };
  /** Prefill — transaction kind. */
  initialKind?: TransactionKind;
  /** Prefill — location. */
  initialLocationId?: string;
}

export function RecordTransactionModal({
  open,
  onClose,
  onRecorded,
  role,
  initialEntityKind,
  fixedEntity,
  initialKind,
  initialLocationId,
}: Props) {
  const allowedKinds = useMemo(() => kindsForRole(role), [role]);

  const [kind, setKind] = useState<TransactionKind>(
    initialKind ?? allowedKinds[0] ?? "adjustment",
  );
  const [entityKind, setEntityKind] = useState<EntityKind>(
    fixedEntity?.kind ?? initialEntityKind ?? "material",
  );
  const [entity, setEntity] = useState<EntityOption | null>(
    fixedEntity
      ? { id: fixedEntity.id, label: fixedEntity.label }
      : null,
  );
  const [locations, setLocations] = useState<InventoryLocationResponse[]>([]);
  const [locationId, setLocationId] = useState<string>(initialLocationId ?? "");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [occurredAt, setOccurredAt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset prefilled fields whenever the modal opens (so reopens don't
  // carry stale state from a previous session).
  useEffect(() => {
    if (!open) return;
    setKind(initialKind ?? allowedKinds[0] ?? "adjustment");
    setEntityKind(fixedEntity?.kind ?? initialEntityKind ?? "material");
    setEntity(
      fixedEntity ? { id: fixedEntity.id, label: fixedEntity.label } : null,
    );
    setLocationId(initialLocationId ?? "");
    setQuantity("");
    setReason("");
    setOccurredAt("");
    setError(null);
  }, [
    open,
    initialKind,
    initialEntityKind,
    initialLocationId,
    fixedEntity,
    allowedKinds,
  ]);

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

  function close() {
    if (submitting) return;
    onClose();
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!entity) {
      setError("Pick an entity.");
      return;
    }
    if (!locationId) {
      setError("Pick a location.");
      return;
    }
    if (!quantity.trim()) {
      setError("Quantity is required.");
      return;
    }
    setSubmitting(true);
    try {
      const body: InventoryTransactionCreate = {
        kind,
        // The kind selector only offers material/supply/product; parts are
        // produced via jobs, not manual transactions (epic #267).
        entity_kind: entityKind as InventoryTransactionCreate["entity_kind"],
        entity_id: entity.id,
        location_id: locationId,
        quantity: quantity.trim(),
      };
      if (reason.trim()) body.reason = reason.trim();
      if (occurredAt.trim()) body.occurred_at = new Date(occurredAt).toISOString();
      const res = await apiClient.post<InventoryTransactionResponse>(
        "/api/v1/inventory/transactions",
        body,
      );
      const loc = locations.find((l) => l.id === locationId);
      const summary = `Recorded ${kind}: ${quantity.trim()} of ${entity.label}${
        loc ? ` at ${loc.name}` : ""
      }`;
      onRecorded(res.data, summary);
      onClose();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not record transaction.";
      setError(
        typeof detail === "string" ? detail : "Could not record transaction.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => (!o ? close() : null)}>
      <DialogContent>
        <DialogTitle>Record transaction</DialogTitle>
        <DialogDescription>
          Logs a new ledger row; on-hand totals refresh on close.
        </DialogDescription>
        <form className="mt-4 space-y-3" onSubmit={onSubmit}>
          {error ? (
            <p
              role="alert"
              data-testid="record-tx-error"
              className="rounded border border-destructive bg-destructive/10 p-2 text-sm text-destructive"
            >
              {error}
            </p>
          ) : null}

          <label className="block text-sm">
            Kind
            <select
              className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              value={kind}
              onChange={(e) => setKind(e.target.value as TransactionKind)}
              disabled={submitting}
              data-testid="record-tx-kind"
            >
              {ALL_KINDS.filter((k) => allowedKinds.includes(k.value)).map(
                (k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ),
              )}
            </select>
          </label>

          {fixedEntity ? null : (
            <>
              <label className="block text-sm">
                Entity kind
                <select
                  className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                  value={entityKind}
                  onChange={(e) => {
                    setEntityKind(e.target.value as EntityKind);
                    setEntity(null);
                  }}
                  disabled={submitting}
                  data-testid="record-tx-entity-kind"
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
                    disabled={submitting}
                    data-testid="record-tx-entity"
                  />
                </div>
              </label>
            </>
          )}

          <label className="block text-sm">
            Location
            <select
              className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
              disabled={submitting}
              data-testid="record-tx-location"
            >
              <option value="">Pick a location…</option>
              {locations.map((loc) => (
                <option key={loc.id} value={loc.id}>
                  {loc.name} ({loc.code})
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
              disabled={submitting}
              required
              data-testid="record-tx-quantity"
            />
          </label>

          <label className="block text-sm">
            Reason (optional)
            <Input
              className="mt-1"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              disabled={submitting}
              data-testid="record-tx-reason"
            />
          </label>

          <label className="block text-sm">
            Occurred at (optional)
            <Input
              className="mt-1"
              type="datetime-local"
              value={occurredAt}
              onChange={(e) => setOccurredAt(e.target.value)}
              disabled={submitting}
              data-testid="record-tx-occurred-at"
            />
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={close}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={submitting}
              data-testid="record-tx-submit"
            >
              {submitting ? (
                <span data-testid="record-tx-spinner">Recording…</span>
              ) : (
                "Record"
              )}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
