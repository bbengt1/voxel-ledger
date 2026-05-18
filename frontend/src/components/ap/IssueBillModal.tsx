/**
 * Confirm modal for issuing a bill. Shows a JE preview (Expense debit /
 * AP credit) computed client-side from the bill totals + the vendor's
 * default expense / AP accounts. Mirrors `IssueInvoiceModal`.
 */
import { useEffect, useState } from "react";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/Dialog";

type BillResponse = components["schemas"]["BillResponse"];
type AccountResponse = components["schemas"]["AccountResponse"];
type VendorResponse = components["schemas"]["VendorResponse"];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  bill: BillResponse;
  onConfirm: () => Promise<void> | void;
  busy: boolean;
}

export function IssueBillModal({
  open,
  onOpenChange,
  bill,
  onConfirm,
  busy,
}: Props) {
  const [accounts, setAccounts] = useState<AccountResponse[]>([]);
  const [vendor, setVendor] = useState<VendorResponse | null>(null);

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
      .get(`/api/v1/vendors/${bill.vendor_id}` as "/api/v1/vendors/{vendor_id}")
      .then((res) => setVendor(res.data as unknown as VendorResponse))
      .catch(() => setVendor(null));
  }, [open, bill.vendor_id]);

  const accountLabel = (id?: string | null) => {
    if (!id) return "(account TBD)";
    const a = accounts.find((x) => x.id === id);
    return a ? `${a.code} · ${a.name}` : id.slice(0, 8);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Issue bill {bill.bill_number}?</DialogTitle>
        <p className="mt-2 text-sm text-muted-foreground">
          Issuing posts the journal entry below and locks the bill. Lines can
          no longer be edited after issuance.
        </p>

        <div
          className="mt-4 rounded-lg border border-border p-3 text-sm"
          data-testid="issue-bill-je-preview"
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
                  {accountLabel(vendor?.default_expense_account_id)} (Expense)
                </td>
                <td className="py-1 pr-2 text-right font-mono">
                  ${bill.subtotal}
                </td>
                <td className="py-1 pr-2 text-right font-mono">—</td>
              </tr>
              {Number.parseFloat(bill.tax_amount) > 0 ? (
                <tr className="border-b border-border/50">
                  <td className="py-1 pr-2">Sales tax payable</td>
                  <td className="py-1 pr-2 text-right font-mono">
                    ${bill.tax_amount}
                  </td>
                  <td className="py-1 pr-2 text-right font-mono">—</td>
                </tr>
              ) : null}
              {Number.parseFloat(bill.discount_amount) > 0 ? (
                <tr className="border-b border-border/50">
                  <td className="py-1 pr-2">Discount (Expense contra)</td>
                  <td className="py-1 pr-2 text-right font-mono">—</td>
                  <td className="py-1 pr-2 text-right font-mono">
                    ${bill.discount_amount}
                  </td>
                </tr>
              ) : null}
              <tr className="border-b border-border/50">
                <td className="py-1 pr-2">
                  {accountLabel(vendor?.default_ap_account_id)} (AP)
                </td>
                <td className="py-1 pr-2 text-right font-mono">—</td>
                <td className="py-1 pr-2 text-right font-mono">
                  ${bill.total_amount}
                </td>
              </tr>
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
            data-testid="issue-bill-confirm-btn"
          >
            {busy ? "Issuing…" : "Issue bill"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
