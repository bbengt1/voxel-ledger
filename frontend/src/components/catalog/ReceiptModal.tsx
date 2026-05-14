import { useState } from "react";

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
  onClose: () => void;
  onRecorded: (updated: MaterialResponse) => void;
}

export function ReceiptModal({ open, materialId, onClose, onRecorded }: Props) {
  const [grams, setGrams] = useState("");
  const [totalCost, setTotalCost] = useState("");
  const [vendor, setVendor] = useState("");
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setGrams("");
    setTotalCost("");
    setVendor("");
    setReference("");
    setNotes("");
    setError(null);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        grams: grams.trim(),
        total_cost: totalCost.trim(),
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
          Adds grams to inventory and updates the running weighted-average
          cost per gram.
        </DialogDescription>
        <form className="mt-4 space-y-3" onSubmit={onSubmit}>
          <label className="block text-sm">
            Grams
            <Input
              className="mt-1"
              inputMode="decimal"
              value={grams}
              onChange={(e) => setGrams(e.target.value)}
              required
              data-testid="receipt-grams"
            />
          </label>
          <label className="block text-sm">
            Total cost
            <Input
              className="mt-1"
              inputMode="decimal"
              value={totalCost}
              onChange={(e) => setTotalCost(e.target.value)}
              required
              data-testid="receipt-total-cost"
            />
          </label>
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
