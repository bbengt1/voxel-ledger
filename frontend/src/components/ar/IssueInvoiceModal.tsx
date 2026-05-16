/**
 * Confirm modal for issuing an invoice. Shows a JE preview (AR debit /
 * revenue credit) computed client-side from the invoice totals + the
 * customer's default accounts.
 */
import { useEffect, useState } from "react";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/Dialog";

type InvoiceResponse = components["schemas"]["InvoiceResponse"];
type AccountResponse = components["schemas"]["AccountResponse"];
type CustomerResponse = components["schemas"]["CustomerResponse"];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  invoice: InvoiceResponse;
  onConfirm: () => Promise<void> | void;
  busy: boolean;
}

export function IssueInvoiceModal({
  open,
  onOpenChange,
  invoice,
  onConfirm,
  busy,
}: Props) {
  const [accounts, setAccounts] = useState<AccountResponse[]>([]);
  const [customer, setCustomer] = useState<CustomerResponse | null>(null);

  useEffect(() => {
    if (!open) return;
    api
      .get("/api/v1/accounts")
      .then((res) => {
        const items = (res.data as { items: AccountResponse[] }).items ?? [];
        setAccounts(items);
      })
      .catch(() => setAccounts([]));
    api
      .get(
        `/api/v1/customers/${invoice.customer_id}` as "/api/v1/customers/{customer_id}",
      )
      .then((res) => setCustomer(res.data as unknown as CustomerResponse))
      .catch(() => setCustomer(null));
  }, [open, invoice.customer_id]);

  const accountLabel = (id?: string | null) => {
    if (!id) return "(account TBD)";
    const a = accounts.find((x) => x.id === id);
    return a ? `${a.code} · ${a.name}` : id.slice(0, 8);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Issue invoice {invoice.invoice_number}?</DialogTitle>
        <p className="mt-2 text-sm text-muted-foreground">
          Issuing posts the journal entry below and locks the invoice. Lines
          can no longer be edited after issuance.
        </p>

        <div
          className="mt-4 rounded-lg border border-border p-3 text-sm"
          data-testid="issue-je-preview"
        >
          <h3 className="font-semibold">Journal entry preview</h3>
          <table className="mt-2 w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                <th className="py-1 pr-2">Account</th>
                <th className="py-1 pr-2 text-right">Debit</th>
                <th className="py-1 pr-2 text-right">Credit</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-border/50">
                <td className="py-1 pr-2">
                  {accountLabel(customer?.default_ar_account_id)} (AR)
                </td>
                <td className="py-1 pr-2 text-right font-mono">
                  ${invoice.total_amount}
                </td>
                <td className="py-1 pr-2 text-right font-mono">—</td>
              </tr>
              <tr className="border-b border-border/50">
                <td className="py-1 pr-2">
                  {accountLabel(customer?.default_revenue_account_id)} (Revenue)
                </td>
                <td className="py-1 pr-2 text-right font-mono">—</td>
                <td className="py-1 pr-2 text-right font-mono">
                  ${invoice.subtotal}
                </td>
              </tr>
              {Number.parseFloat(invoice.discount_amount) > 0 ? (
                <tr className="border-b border-border/50">
                  <td className="py-1 pr-2">Discount (Revenue contra)</td>
                  <td className="py-1 pr-2 text-right font-mono">
                    ${invoice.discount_amount}
                  </td>
                  <td className="py-1 pr-2 text-right font-mono">—</td>
                </tr>
              ) : null}
              {Number.parseFloat(invoice.tax_amount) > 0 ? (
                <tr className="border-b border-border/50">
                  <td className="py-1 pr-2">Sales tax payable</td>
                  <td className="py-1 pr-2 text-right font-mono">—</td>
                  <td className="py-1 pr-2 text-right font-mono">
                    ${invoice.tax_amount}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            Cancel
          </Button>
          <Button
            onClick={() => void onConfirm()}
            disabled={busy}
            data-testid="issue-confirm-btn"
          >
            {busy ? "Issuing…" : "Issue invoice"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
