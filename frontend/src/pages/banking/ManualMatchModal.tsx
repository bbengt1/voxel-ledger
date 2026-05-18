/**
 * Modal: paste a journal_entry_id and match a bank tx to it.
 * Free-text UUID input — operator copies from the journal-entries list.
 */
import { useState } from "react";

import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";

interface Props {
  txId: string;
  open: boolean;
  onOpenChange: (next: boolean) => void;
  onDone: () => void;
}

export function ManualMatchModal({ txId, open, onOpenChange, onDone }: Props) {
  const [jeId, setJeId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!jeId.trim()) {
      setError("Enter a journal entry id.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await apiClient.post(`/api/v1/bank-transactions/${txId}/match`, {
        journal_entry_id: jeId.trim(),
      });
      onDone();
      onOpenChange(false);
      setJeId("");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not match.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="manual-match-modal">
        <DialogTitle>Match to journal entry</DialogTitle>
        <div className="mt-3 space-y-3">
          <label className="block text-sm">
            Journal entry ID
            <Input
              value={jeId}
              onChange={(e) => setJeId(e.target.value)}
              placeholder="paste a UUID"
              data-testid="manual-match-je-id"
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
              data-testid="manual-match-submit"
            >
              {submitting ? "Matching…" : "Match"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
