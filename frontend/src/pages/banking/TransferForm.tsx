/**
 * `/banking/transfer` — move money between two asset accounts. Posts a
 * single body; the transfer is pushed to QuickBooks async (#318), so there
 * is no local journal entry to navigate to.
 */
import { useState } from "react";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { BankAccountPicker } from "@/components/banking/BankAccountPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type TransferRequest = components["schemas"]["InterAccountTransferRequest"];

function defaultLocalDateTime(): string {
  // <input type="datetime-local"> wants YYYY-MM-DDTHH:mm (no seconds, no TZ).
  const now = new Date();
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

export function TransferFormPage() {
  const [fromId, setFromId] = useState("");
  const [toId, setToId] = useState("");
  const [amount, setAmount] = useState("");
  const [occurredAt, setOccurredAt] = useState(defaultLocalDateTime());
  const [memo, setMemo] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function submit() {
    if (!fromId || !toId) {
      setError("Pick both accounts.");
      return;
    }
    if (fromId === toId) {
      setError("From and To must be different accounts.");
      return;
    }
    const n = Number.parseFloat(amount);
    if (!Number.isFinite(n) || n <= 0) {
      setError("Amount must be greater than 0.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const body: TransferRequest = {
        from_account_id: fromId,
        to_account_id: toId,
        amount,
        occurred_at: new Date(occurredAt).toISOString(),
      };
      if (memo.trim()) body.memo = memo.trim();
      await apiClient.post("/api/v1/inter-account-transfers", body);
      // QBO replace-mode (#318): the transfer is pushed to QuickBooks async;
      // there is no local journal entry to link to.
      setSuccess("Transfer recorded — queued to QuickBooks.");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not transfer.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Inter-account transfer</h1>
      </header>

      <div className="grid grid-cols-2 gap-3 rounded-lg border border-border p-4">
        <label className="block text-sm">
          From account
          <BankAccountPicker
            value={fromId}
            onChange={setFromId}
            data-testid="transfer-from"
          />
        </label>
        <label className="block text-sm">
          To account
          <BankAccountPicker
            value={toId}
            onChange={setToId}
            data-testid="transfer-to"
          />
        </label>
        <label className="block text-sm">
          Amount
          <Input
            type="number"
            step="0.01"
            min={0}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            data-testid="transfer-amount"
          />
        </label>
        <label className="block text-sm">
          Occurred at
          <Input
            type="datetime-local"
            value={occurredAt}
            onChange={(e) => setOccurredAt(e.target.value)}
            data-testid="transfer-occurred-at"
          />
        </label>
        <label className="col-span-2 block text-sm">
          Memo
          <Input
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
            data-testid="transfer-memo"
          />
        </label>
      </div>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      {success ? (
        <p className="text-sm text-emerald-700" data-testid="transfer-success">
          {success}
        </p>
      ) : null}

      <div className="flex gap-2">
        <Button
          disabled={submitting}
          onClick={() => void submit()}
          data-testid="transfer-submit"
        >
          {submitting ? "Transferring…" : "Transfer"}
        </Button>
      </div>
    </section>
  );
}
