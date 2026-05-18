/**
 * Modal: post a journal entry from a bank transaction. The bank-side line
 * is pre-populated with the correct debit/credit sign so the operator only
 * picks the contra account.
 *
 * Convention used:
 *   - tx.amount > 0  → money in (debit the bank account)
 *   - tx.amount < 0  → money out (credit the bank account)
 */
import { useMemo, useState } from "react";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { AccountPicker } from "@/components/ar/AccountPicker";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";

type Tx = components["schemas"]["BankTransactionResponse"];
type PostBody = components["schemas"]["BankPostJournalEntryRequest"];
type LineInput = components["schemas"]["BankJournalEntryLineInput"];

interface Props {
  tx: Tx | null;
  open: boolean;
  onOpenChange: (next: boolean) => void;
  onDone: () => void;
}

export function PostJournalEntryModal({
  tx,
  open,
  onOpenChange,
  onDone,
}: Props) {
  const [contraAccountId, setContraAccountId] = useState("");
  const [description, setDescription] = useState("");
  const [memo, setMemo] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const amountAbs = useMemo(() => {
    if (!tx) return "0.00";
    const n = Number.parseFloat(tx.amount);
    return Number.isFinite(n) ? Math.abs(n).toFixed(2) : "0.00";
  }, [tx]);

  const isInflow = useMemo(() => {
    if (!tx) return true;
    return Number.parseFloat(tx.amount) >= 0;
  }, [tx]);

  async function submit() {
    if (!tx) return;
    if (!contraAccountId) {
      setError("Pick a contra account.");
      return;
    }
    if (!description.trim()) {
      setError("Description is required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      // tx.amount sign drives which side the bank account sits on.
      const bankLine: LineInput = isInflow
        ? {
            account_id: tx.account_id,
            debit: amountAbs,
            credit: "0",
            line_number: 1,
          }
        : {
            account_id: tx.account_id,
            debit: "0",
            credit: amountAbs,
            line_number: 1,
          };
      const contraLine: LineInput = isInflow
        ? {
            account_id: contraAccountId,
            debit: "0",
            credit: amountAbs,
            line_number: 2,
          }
        : {
            account_id: contraAccountId,
            debit: amountAbs,
            credit: "0",
            line_number: 2,
          };
      if (memo.trim()) {
        bankLine.memo = memo.trim();
        contraLine.memo = memo.trim();
      }
      const body: PostBody = {
        description: description.trim(),
        posted_at: new Date().toISOString(),
        lines: [bankLine, contraLine],
      };
      await apiClient.post(
        `/api/v1/bank-transactions/${tx.id}/post-journal-entry`,
        body,
      );
      onDone();
      onOpenChange(false);
      setContraAccountId("");
      setDescription("");
      setMemo("");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : "Could not post journal entry.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="post-je-modal">
        <DialogTitle>Post journal entry</DialogTitle>
        {tx ? (
          <div className="mt-3 space-y-3 text-sm">
            <div className="rounded-md border border-border bg-accent/30 p-2 text-xs">
              <div className="font-mono">{tx.description}</div>
              <div className="font-mono">
                {tx.occurred_on} · {tx.amount}
              </div>
            </div>

            <div className="space-y-1 rounded-md border border-border p-2 text-xs">
              <div className="font-semibold">
                Line 1 (bank account, prefilled)
              </div>
              <div>Account: bank</div>
              <div>
                {isInflow
                  ? `Debit ${amountAbs}`
                  : `Credit ${amountAbs}`}
              </div>
            </div>

            <label className="block">
              Contra account
              <AccountPicker
                value={contraAccountId}
                onChange={setContraAccountId}
                data-testid="post-je-contra"
              />
            </label>
            <p className="text-xs text-muted-foreground">
              Auto-fill: {isInflow ? "credit" : "debit"} {amountAbs}.
            </p>

            <label className="block">
              Description
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                data-testid="post-je-description"
              />
            </label>

            <label className="block">
              Memo
              <Input
                value={memo}
                onChange={(e) => setMemo(e.target.value)}
                data-testid="post-je-memo"
              />
            </label>

            {error ? (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            ) : null}

            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={submitting}
              >
                Cancel
              </Button>
              <Button
                onClick={() => void submit()}
                disabled={submitting}
                data-testid="post-je-submit"
              >
                {submitting ? "Posting…" : "Post + match"}
              </Button>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
