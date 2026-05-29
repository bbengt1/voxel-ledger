import { useMemo, useState } from "react";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type MaterialResponse = components["schemas"]["MaterialResponse"];

interface Props {
  open: boolean;
  materialId: string;
  spoolWeightGrams: number;
  onClose: () => void;
  onRecorded: (updated: MaterialResponse) => void;
}

function round2(value: number): string {
  if (!Number.isFinite(value)) return "0.00";
  return value.toFixed(2);
}

export function ReceiptModal({
  open,
  materialId,
  spoolWeightGrams,
  onClose,
  onRecorded,
}: Props) {
  const [spools, setSpools] = useState("");
  const [extraGrams, setExtraGrams] = useState("");
  const [pricePerSpool, setPricePerSpool] = useState("");
  const [vendor, setVendor] = useState("");
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setSpools("");
    setExtraGrams("");
    setPricePerSpool("");
    setVendor("");
    setReference("");
    setNotes("");
    setError(null);
  }

  const preview = useMemo(() => {
    const s = Math.trunc(Number(spools) || 0);
    const extra = Number(extraGrams) || 0;
    const price = Number(pricePerSpool) || 0;
    if (spoolWeightGrams <= 0) return null;
    const grams = s * spoolWeightGrams + extra;
    const totalCost = price * (s + extra / spoolWeightGrams);
    if (grams <= 0) return null;
    return { grams, totalCost };
  }, [spools, extraGrams, pricePerSpool, spoolWeightGrams]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const s = Math.trunc(Number(spools) || 0);
      if (s < 0 || !Number.isInteger(s)) {
        setError("Spools must be a non-negative whole number.");
        setSubmitting(false);
        return;
      }
      const body: Record<string, unknown> = {
        spools: s,
        extra_grams: extraGrams.trim() || "0",
        price_per_spool: pricePerSpool.trim() || "0",
      };
      if (vendor.trim()) body["vendor"] = vendor.trim();
      if (reference.trim()) body["reference"] = reference.trim();
      if (notes.trim()) body["notes"] = notes.trim();
      const res = await apiClient.post<MaterialResponse>(
        `/api/v1/materials/${materialId}/receipts`,
        body,
      );
      onRecorded(res.data);
      reset();
      onClose();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not record receipt.";
      setError(typeof detail === "string" ? detail : "Could not record receipt.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          reset();
          onClose();
        }
      }}
    >
      <DialogContent>
        <DialogTitle>Record receipt</DialogTitle>
        <DialogDescription>
          Enter the number of spools (whole), any extra grams measured from a
          partial spool, and the price per spool. Adds to inventory and
          updates the running weighted-average cost per gram.
        </DialogDescription>
        <form className="mt-4 space-y-3" onSubmit={onSubmit}>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              Spools
              <Input
                className="mt-1"
                inputMode="numeric"
                value={spools}
                onChange={(e) => setSpools(e.target.value)}
                required
                data-testid="receipt-spools"
              />
            </label>
            <label className="block text-sm">
              Extra grams (optional)
              <Input
                className="mt-1"
                inputMode="decimal"
                value={extraGrams}
                onChange={(e) => setExtraGrams(e.target.value)}
                data-testid="receipt-extra-grams"
              />
            </label>
          </div>
          <label className="block text-sm">
            Price per spool ($)
            <Input
              className="mt-1"
              inputMode="decimal"
              value={pricePerSpool}
              onChange={(e) => setPricePerSpool(e.target.value)}
              required
              data-testid="receipt-price-per-spool"
            />
          </label>
          {preview ? (
            <p className="text-xs text-muted-foreground" data-testid="receipt-preview">
              Total:{" "}
              <span className="font-medium tabular-nums">
                {round2(preview.grams)} g
              </span>{" "}
              @ ${round2(Number(pricePerSpool) || 0)}/spool →{" "}
              <span className="font-medium tabular-nums">
                ${round2(preview.totalCost)}
              </span>
            </p>
          ) : null}
          <label className="block text-sm">
            Vendor
            <Input
              className="mt-1"
              value={vendor}
              onChange={(e) => setVendor(e.target.value)}
            />
          </label>
          <label className="block text-sm">
            Reference
            <Input
              className="mt-1"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
            />
          </label>
          <label className="block text-sm">
            Notes
            <Input
              className="mt-1"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>

          {error ? (
            <p
              role="alert"
              data-testid="receipt-error"
              className="text-sm text-destructive"
            >
              {error}
            </p>
          ) : null}

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                reset();
                onClose();
              }}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting} data-testid="receipt-submit">
              {submitting ? "Recording…" : "Record"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
