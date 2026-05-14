/**
 * Modal to POST an inventory transfer (out + in pair).
 *
 * Validates from-location != to-location client-side. Backend gates this
 * to owner/production roles — the parent component should only render
 * the trigger for those roles.
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

type InventoryTransferCreate =
  components["schemas"]["InventoryTransferCreate"];
type InventoryTransferResponse =
  components["schemas"]["InventoryTransferResponse"];
type InventoryLocationResponse =
  components["schemas"]["InventoryLocationResponse"];

interface Props {
  open: boolean;
  onClose: () => void;
  onTransferred: (result: InventoryTransferResponse) => void;
  /** Prefill — entity kind. */
  initialEntityKind?: EntityKind;
  /** Fix the entity (hide the picker). */
  fixedEntity?: EntityOption & { kind: EntityKind };
}

export function TransferStockModal({
  open,
  onClose,
  onTransferred,
  initialEntityKind,
  fixedEntity,
}: Props) {
  const [entityKind, setEntityKind] = useState<EntityKind>(
    fixedEntity?.kind ?? initialEntityKind ?? "material",
  );
  const [entity, setEntity] = useState<EntityOption | null>(
    fixedEntity
      ? { id: fixedEntity.id, label: fixedEntity.label }
      : null,
  );
  const [locations, setLocations] = useState<InventoryLocationResponse[]>([]);
  const [fromId, setFromId] = useState("");
  const [toId, setToId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [occurredAt, setOccurredAt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setEntityKind(fixedEntity?.kind ?? initialEntityKind ?? "material");
    setEntity(
      fixedEntity ? { id: fixedEntity.id, label: fixedEntity.label } : null,
    );
    setFromId("");
    setToId("");
    setQuantity("");
    setReason("");
    setOccurredAt("");
    setError(null);
  }, [open, initialEntityKind, fixedEntity]);

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

  const sameLocation = useMemo(
    () => fromId !== "" && toId !== "" && fromId === toId,
    [fromId, toId],
  );

  const canSubmit =
    !!entity &&
    fromId !== "" &&
    toId !== "" &&
    !sameLocation &&
    quantity.trim() !== "" &&
    !submitting;

  function close() {
    if (submitting) return;
    onClose();
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || !entity) return;
    setSubmitting(true);
    setError(null);
    try {
      const body: InventoryTransferCreate = {
        entity_kind: entityKind,
        entity_id: entity.id,
        from_location_id: fromId,
        to_location_id: toId,
        quantity: quantity.trim(),
      };
      if (reason.trim()) body.reason = reason.trim();
      if (occurredAt.trim()) body.occurred_at = new Date(occurredAt).toISOString();
      const res = await apiClient.post<InventoryTransferResponse>(
        "/api/v1/inventory/transactions/transfer",
        body,
      );
      onTransferred(res.data);
      onClose();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not record transfer.";
      setError(typeof detail === "string" ? detail : "Could not record transfer.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => (!o ? close() : null)}>
      <DialogContent>
        <DialogTitle>Transfer stock</DialogTitle>
        <DialogDescription>
          Moves quantity from one location to another. Two ledger rows are
          written with a shared transfer_pair_id.
        </DialogDescription>
        <form className="mt-4 space-y-3" onSubmit={onSubmit}>
          {error ? (
            <p
              role="alert"
              data-testid="transfer-error"
              className="rounded border border-destructive bg-destructive/10 p-2 text-sm text-destructive"
            >
              {error}
            </p>
          ) : null}

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
                  data-testid="transfer-entity-kind"
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
                    data-testid="transfer-entity"
                  />
                </div>
              </label>
            </>
          )}

          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              From
              <select
                className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                value={fromId}
                onChange={(e) => setFromId(e.target.value)}
                disabled={submitting}
                data-testid="transfer-from"
              >
                <option value="">Pick…</option>
                {locations.map((loc) => (
                  <option key={loc.id} value={loc.id}>
                    {loc.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              To
              <select
                className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                value={toId}
                onChange={(e) => setToId(e.target.value)}
                disabled={submitting}
                data-testid="transfer-to"
              >
                <option value="">Pick…</option>
                {locations.map((loc) => (
                  <option key={loc.id} value={loc.id}>
                    {loc.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {sameLocation ? (
            <p
              role="alert"
              data-testid="transfer-same-location"
              className="text-xs text-destructive"
            >
              From and To must be different locations.
            </p>
          ) : null}

          <label className="block text-sm">
            Quantity
            <Input
              className="mt-1"
              inputMode="decimal"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              disabled={submitting}
              required
              data-testid="transfer-quantity"
            />
          </label>

          <label className="block text-sm">
            Reason (optional)
            <Input
              className="mt-1"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              disabled={submitting}
              data-testid="transfer-reason"
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
              disabled={!canSubmit}
              data-testid="transfer-submit"
            >
              {submitting ? (
                <span data-testid="transfer-spinner">Transferring…</span>
              ) : (
                "Transfer"
              )}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
