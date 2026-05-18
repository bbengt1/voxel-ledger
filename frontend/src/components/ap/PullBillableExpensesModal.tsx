/**
 * Modal for pulling unbilled expenses onto an invoice. Surfaced from the
 * invoice composer once a customer is picked. Fetches
 * `/api/v1/billable-expenses?customer_id=...`, renders a checkbox list,
 * and on confirm hands the selected rows back to the parent which appends
 * them as `billable_source`-tagged invoice line drafts.
 */
import { useEffect, useState } from "react";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/Dialog";

type UnbilledRow = components["schemas"]["UnbilledRow"];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customerId: string;
  onConfirm: (selected: UnbilledRow[]) => void;
}

function withMarkup(amountStr: string, markupPct: string): string {
  const amt = Number.parseFloat(amountStr);
  const pct = Number.parseFloat(markupPct);
  if (!Number.isFinite(amt)) return amountStr;
  const m = Number.isFinite(pct) ? pct : 0;
  return (amt * (1 + m / 100)).toFixed(2);
}

export function PullBillableExpensesModal({
  open,
  onOpenChange,
  customerId,
  onConfirm,
}: Props) {
  const [rows, setRows] = useState<UnbilledRow[]>([]);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !customerId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/billable-expenses", { params: { customer_id: customerId } })
      .then((res) => {
        if (cancelled) return;
        setRows(res.data.items ?? []);
        setPicked({});
      })
      .catch(() => {
        if (!cancelled) {
          setError("Could not load billable expenses.");
          setRows([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, customerId]);

  function toggle(rowKey: string) {
    setPicked((p) => ({ ...p, [rowKey]: !p[rowKey] }));
  }

  function rowKey(r: UnbilledRow): string {
    return `${r.source_kind}:${r.source_id}`;
  }

  function confirm() {
    const selected = rows.filter((r) => picked[rowKey(r)]);
    onConfirm(selected);
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogTitle>Pull billable expenses</DialogTitle>
        <p className="mt-1 text-xs text-muted-foreground">
          Pick the unbilled bill items or expense-claim lines to add to this
          invoice. Markup is applied server-side on issue.
        </p>

        {error ? (
          <p
            role="alert"
            className="mt-2 text-sm text-destructive"
            data-testid="pull-billable-error"
          >
            {error}
          </p>
        ) : null}

        {loading ? (
          <p className="mt-3 text-sm text-muted-foreground">Loading…</p>
        ) : rows.length === 0 ? (
          <p
            className="mt-3 text-sm text-muted-foreground"
            data-testid="pull-billable-empty"
          >
            No unbilled expenses for this customer.
          </p>
        ) : (
          <table className="mt-3 w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                <th className="py-1 pr-2"></th>
                <th className="py-1 pr-2">Source</th>
                <th className="py-1 pr-2">Description</th>
                <th className="py-1 pr-2">Date</th>
                <th className="py-1 pr-2 text-right">Amount</th>
                <th className="py-1 pr-2 text-right">Markup</th>
                <th className="py-1 pr-2 text-right">Billed</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const k = rowKey(r);
                return (
                  <tr
                    key={k}
                    className="border-b border-border/50"
                    data-testid={`pull-row-${k}`}
                  >
                    <td className="py-1 pr-2">
                      <input
                        type="checkbox"
                        checked={Boolean(picked[k])}
                        onChange={() => toggle(k)}
                        data-testid={`pull-check-${k}`}
                      />
                    </td>
                    <td className="py-1 pr-2 text-xs">
                      <span className="rounded border border-border bg-muted/30 px-1">
                        {r.source_kind === "bill_item"
                          ? `bill ${r.bill_number ?? ""}`
                          : `claim ${r.claim_number ?? ""}`}
                      </span>
                    </td>
                    <td className="py-1 pr-2">{r.description}</td>
                    <td className="py-1 pr-2 text-xs">
                      {new Date(r.occurred_on).toLocaleDateString()}
                    </td>
                    <td className="py-1 pr-2 text-right font-mono">
                      ${r.amount}
                    </td>
                    <td className="py-1 pr-2 text-right font-mono">
                      {r.markup_percent}%
                    </td>
                    <td className="py-1 pr-2 text-right font-mono">
                      ${withMarkup(r.amount, r.markup_percent)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={confirm}
            data-testid="pull-billable-confirm-btn"
            disabled={rows.length === 0}
          >
            Add selected
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
