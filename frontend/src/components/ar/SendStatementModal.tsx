/**
 * Modal launched from CustomerDetail. Operator picks an optional date
 * range and an include-paid toggle; submitting enqueues an email via
 * `/api/v1/customers/{id}/statements/send` and closes the modal. Send is
 * fire-and-forget — the parent shows a banner on success.
 *
 * Note: the backend endpoint accepts only `include_paid` (as a query
 * param) and an optional null body today. We still surface the date
 * range inputs because the spec calls for them; they are sent in the
 * body as forward-compatible hints. Backend can choose to honor them
 * when the request body schema grows.
 */
import { useState } from "react";

import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customerId: string;
  onSent: () => void;
}

export function SendStatementModal({
  open,
  onOpenChange,
  customerId,
  onSent,
}: Props) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [includePaid, setIncludePaid] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      // Body is forward-compatible; include_paid lives in the query string.
      const body: Record<string, unknown> = { include_paid: includePaid };
      if (from) body["from_date"] = from;
      if (to) body["to_date"] = to;
      await apiClient.post(
        `/api/v1/customers/${customerId}/statements/send?include_paid=${
          includePaid ? "true" : "false"
        }`,
        body,
      );
      onOpenChange(false);
      onSent();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : "Could not send statement.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Send statement</DialogTitle>
        <DialogDescription>
          Queues an email to the customer with a statement of activity.
        </DialogDescription>

        <div className="mt-4 grid grid-cols-2 gap-3">
          <label className="block text-sm">
            From
            <Input
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              data-testid="statement-from"
            />
          </label>
          <label className="block text-sm">
            To
            <Input
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              data-testid="statement-to"
            />
          </label>
        </div>
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={includePaid}
            onChange={(e) => setIncludePaid(e.target.checked)}
            data-testid="statement-include-paid"
          />
          Include paid invoices
        </label>

        {error ? (
          <p role="alert" className="mt-2 text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <div className="mt-4 flex justify-end gap-2">
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            disabled={busy}
            onClick={() => void submit()}
            data-testid="statement-send-btn"
          >
            {busy ? "Queueing…" : "Send"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
