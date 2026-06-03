/**
 * `/bills/:id` — bill detail with read-only header + line table, state
 * action bar (Issue / Void / Record payment), PDF link, and a JE-preview
 * Issue modal mirroring InvoiceDetail.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { IssueBillModal } from "@/components/ap/IssueBillModal";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type BillResponse = components["schemas"]["BillResponse"];

const WRITE_ROLES: readonly string[] = ["owner", "bookkeeper"];

export function BillDetailPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? WRITE_ROLES.includes(role) : false;

  const [bill, setBill] = useState<BillResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [issueOpen, setIssueOpen] = useState(false);

  const refetch = useCallback(async () => {
    if (!id) return;
    try {
      const res = await api.get(
        `/api/v1/bills/${id}` as "/api/v1/bills/{bill_id}",
      );
      setBill(res.data as unknown as BillResponse);
    } catch {
      setError("Failed to load bill.");
    }
  }, [id]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  async function issueConfirm() {
    if (!id) return;
    setBusy(true);
    try {
      await apiClient.post(`/api/v1/bills/${id}/issue`, null);
      setIssueOpen(false);
      await refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not issue bill.");
    } finally {
      setBusy(false);
    }
  }

  async function voidBill() {
    if (!id) return;
    if (!window.confirm("Void this bill? This is permanent.")) return;
    setBusy(true);
    try {
      await apiClient.post(`/api/v1/bills/${id}/void`, null);
      await refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not void bill.");
    } finally {
      setBusy(false);
    }
  }

  function openPdf() {
    if (!id) return;
    window.open(`/api/v1/bills/${id}/pdf`, "_blank", "noopener,noreferrer");
  }

  if (!bill) {
    return error ? (
      <p role="alert" className="text-sm text-destructive">
        {error}
      </p>
    ) : (
      <p className="text-sm text-muted-foreground">Loading…</p>
    );
  }

  const isDraft = bill.state === "draft";
  const canIssue = isDraft;
  const canVoid = bill.state === "issued" || bill.state === "overdue";
  const canRecordPayment =
    bill.state === "issued" ||
    bill.state === "partially_paid" ||
    bill.state === "overdue";

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Bill {bill.bill_number}</h1>
          <p className="text-sm text-muted-foreground">
            State: <span data-testid="bill-state">{bill.state}</span>
            {bill.issued_at ? (
              <> · issued {new Date(bill.issued_at).toLocaleDateString()}</>
            ) : null}
            {bill.due_at ? (
              <> · due {new Date(bill.due_at).toLocaleDateString()}</>
            ) : null}
            {bill.vendor_invoice_number ? (
              <> · vendor inv {bill.vendor_invoice_number}</>
            ) : null}
          </p>
        </div>
        <div className="flex gap-2">
          {isDraft && canWrite ? (
            <Button asChild variant="outline">
              <Link to={`/bills/${bill.id}/edit`}>Edit</Link>
            </Button>
          ) : null}
          <Button variant="outline" onClick={openPdf} data-testid="bill-pdf">
            <a
              href={`/api/v1/bills/${bill.id}/pdf`}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="bill-pdf-link"
              onClick={(e) => e.stopPropagation()}
            >
              Download PDF
            </a>
          </Button>
          <Button variant="outline" asChild>
            <Link to="/bills">Back</Link>
          </Button>
        </div>
      </header>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {canWrite ? (
        <div className="flex flex-wrap gap-2" data-testid="bill-actions">
          {canIssue ? (
            <Button
              disabled={busy}
              onClick={() => setIssueOpen(true)}
              data-testid="action-issue"
            >
              Issue
            </Button>
          ) : null}
          {canVoid ? (
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() => void voidBill()}
              data-testid="action-void"
            >
              Void
            </Button>
          ) : null}
          {canRecordPayment ? (
            <Button
              variant="secondary"
              onClick={() =>
                navigate(`/bill-payments/new?bill_id=${bill.id}`)
              }
              data-testid="action-record-payment"
            >
              Record payment
            </Button>
          ) : null}
        </div>
      ) : null}

      <div className="rounded-lg border border-border p-4">
        <h2 className="text-sm font-semibold">Lines</h2>
        <div className="overflow-x-auto">
          <table className="mt-2 w-full min-w-[40rem] table-fixed border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                <th className="py-2 pr-2">#</th>
                <th className="py-2 pr-2">Kind</th>
                <th className="py-2 pr-2">Description</th>
                <th className="py-2 pr-2 text-right">Qty</th>
                <th className="py-2 pr-2 text-right">Unit</th>
                <th className="py-2 pr-2 text-right">Extended</th>
              </tr>
            </thead>
            <tbody>
              {(bill.items ?? []).map((it) => (
                <tr key={it.id} className="border-b border-border/50">
                  <td className="py-2 pr-2 font-mono text-xs">
                    {it.line_number}
                  </td>
                  <td className="py-2 pr-2">{it.kind}</td>
                  <td className="py-2 pr-2">{it.description}</td>
                  <td className="py-2 pr-2 text-right font-mono">
                    {it.quantity}
                  </td>
                  <td className="py-2 pr-2 text-right font-mono">
                    ${it.unit_price}
                  </td>
                  <td className="py-2 pr-2 text-right font-mono">
                    ${it.extended_amount}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-border p-4 text-sm">
          <h2 className="font-semibold">Totals</h2>
          <dl className="mt-2 grid grid-cols-2 gap-y-1">
            <dt className="text-muted-foreground">Subtotal</dt>
            <dd className="text-right font-mono">${bill.subtotal}</dd>
            <dt className="text-muted-foreground">Discount</dt>
            <dd className="text-right font-mono">−${bill.discount_amount}</dd>
            <dt className="text-muted-foreground">Tax</dt>
            <dd className="text-right font-mono">${bill.tax_amount}</dd>
            <dt className="font-semibold">Total</dt>
            <dd className="text-right font-mono font-semibold">
              ${bill.total_amount}
            </dd>
            <dt className="text-muted-foreground">Paid</dt>
            <dd className="text-right font-mono">${bill.amount_paid}</dd>
            <dt className="font-semibold">Outstanding</dt>
            <dd className="text-right font-mono font-semibold">
              ${bill.amount_outstanding}
            </dd>
          </dl>
        </div>
        <div className="rounded-lg border border-border p-4 text-sm">
          <h2 className="font-semibold">Notes</h2>
          {bill.notes ? (
            <p className="mt-2 whitespace-pre-line text-xs text-muted-foreground">
              {bill.notes}
            </p>
          ) : (
            <p className="mt-2 text-xs text-muted-foreground">No notes.</p>
          )}
        </div>
      </div>

      <IssueBillModal
        open={issueOpen}
        onOpenChange={setIssueOpen}
        bill={bill}
        onConfirm={issueConfirm}
        busy={busy}
      />
    </section>
  );
}
