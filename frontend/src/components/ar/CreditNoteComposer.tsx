/**
 * Inline composer for creating + issuing a credit note against an invoice.
 * Launched from the invoice detail action bar.
 */
import { useState } from "react";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type CreditNoteCreate = components["schemas"]["CreditNoteCreate"];
type CreditNoteResponse = components["schemas"]["CreditNoteResponse"];

const REASONS = [
  "return",
  "discount",
  "billing_error",
  "goodwill",
  "other",
] as const;

interface Props {
  invoiceId: string;
  onClose: () => void;
  onIssued: () => void;
}

export function CreditNoteComposer({ invoiceId, onClose, onIssued }: Props) {
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState<(typeof REASONS)[number]>("return");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!amount || Number.parseFloat(amount) <= 0) {
      setError("Amount must be greater than 0.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body: CreditNoteCreate = {
        invoice_id: invoiceId,
        reason,
        total_amount: amount,
      };
      if (notes.trim()) body.notes = notes.trim();
      const res = await api.post("/api/v1/credit-notes", body);
      const note = res.data as unknown as CreditNoteResponse;
      await apiClient.post(`/api/v1/credit-notes/${note.id}/issue`);
      onIssued();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not issue credit note.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="space-y-3 rounded-lg border border-border bg-muted/30 p-4"
      data-testid="credit-note-composer"
    >
      <h3 className="text-sm font-semibold">Issue credit note</h3>
      <div className="grid grid-cols-2 gap-3">
        <label className="block text-sm">
          Reason
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={reason}
            onChange={(e) =>
              setReason(e.target.value as (typeof REASONS)[number])
            }
            data-testid="credit-note-reason"
          >
            {REASONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          Amount
          <Input
            type="number"
            step="0.01"
            min={0}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            data-testid="credit-note-amount"
          />
        </label>
      </div>
      <label className="block text-sm">
        Notes
        <textarea
          className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          data-testid="credit-note-notes"
        />
      </label>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button
          onClick={() => void submit()}
          disabled={busy}
          data-testid="credit-note-submit"
        >
          {busy ? "Issuing…" : "Issue credit note"}
        </Button>
      </div>
    </div>
  );
}
