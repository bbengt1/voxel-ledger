/**
 * `/invoices/:id` — invoice detail with read-only header + line table,
 * state action bar (Issue / Void / Record-payment / Issue-credit-note /
 * Issue-debit-note), PDF download, and a history tab listing issued
 * credit + debit notes.
 *
 * Issue flow opens a confirm modal with the journal-entry preview before
 * calling `/issue`. PDF download opens `/api/v1/invoices/{id}/pdf` in a
 * new tab — no in-app modal per Doherty/UX rules.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { CreditNoteComposer } from "@/components/ar/CreditNoteComposer";
import { DebitNoteComposer } from "@/components/ar/DebitNoteComposer";
import { IssueInvoiceModal } from "@/components/ar/IssueInvoiceModal";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type InvoiceResponse = components["schemas"]["InvoiceResponse"];
type CreditNoteResponse = components["schemas"]["CreditNoteResponse"];
type DebitNoteResponse = components["schemas"]["DebitNoteResponse"];

const WRITE_ROLES: readonly string[] = ["owner", "sales", "bookkeeper"];

type Inline = "none" | "credit" | "debit";

export function InvoiceDetailPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? WRITE_ROLES.includes(role) : false;

  const [invoice, setInvoice] = useState<InvoiceResponse | null>(null);
  const [creditNotes, setCreditNotes] = useState<CreditNoteResponse[]>([]);
  const [debitNotes, setDebitNotes] = useState<DebitNoteResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [issueOpen, setIssueOpen] = useState(false);
  const [inline, setInline] = useState<Inline>("none");

  const refetch = useCallback(async () => {
    if (!id) return;
    try {
      const res = await api.get(
        `/api/v1/invoices/${id}` as "/api/v1/invoices/{invoice_id}",
      );
      setInvoice(res.data as unknown as InvoiceResponse);
    } catch {
      setError("Failed to load invoice.");
    }
  }, [id]);

  const refetchNotes = useCallback(async () => {
    if (!id) return;
    try {
      const cn = await api.get("/api/v1/credit-notes", {
        params: { invoice_id: id },
      });
      setCreditNotes(cn.data.items);
    } catch {
      setCreditNotes([]);
    }
    try {
      const dn = await api.get("/api/v1/debit-notes", {
        params: { invoice_id: id },
      });
      setDebitNotes(dn.data.items);
    } catch {
      setDebitNotes([]);
    }
  }, [id]);

  useEffect(() => {
    void refetch();
    void refetchNotes();
  }, [refetch, refetchNotes]);

  async function issueConfirm() {
    if (!id) return;
    setBusy(true);
    try {
      await apiClient.post(`/api/v1/invoices/${id}/issue`, null);
      setIssueOpen(false);
      await refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not issue invoice.");
    } finally {
      setBusy(false);
    }
  }

  async function voidInvoice() {
    if (!id) return;
    if (!window.confirm("Void this invoice? This is permanent.")) return;
    setBusy(true);
    try {
      await apiClient.post(`/api/v1/invoices/${id}/void`, null);
      await refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not void invoice.");
    } finally {
      setBusy(false);
    }
  }

  function openPdf() {
    if (!id) return;
    window.open(`/api/v1/invoices/${id}/pdf`, "_blank", "noopener,noreferrer");
  }

  if (!invoice) {
    return error ? (
      <p role="alert" className="text-sm text-destructive">
        {error}
      </p>
    ) : (
      <p className="text-sm text-muted-foreground">Loading…</p>
    );
  }

  const isDraft = invoice.state === "draft";
  const canIssue = isDraft;
  const canVoid =
    invoice.state === "issued" || invoice.state === "overdue";
  const canRecordPayment =
    invoice.state === "issued" ||
    invoice.state === "partially_paid" ||
    invoice.state === "overdue";
  const canIssueNotes = canRecordPayment || invoice.state === "paid";

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">
            Invoice {invoice.invoice_number}
          </h1>
          <p className="text-sm text-muted-foreground">
            State: <span data-testid="invoice-state">{invoice.state}</span>
            {invoice.issued_at ? (
              <> · issued {new Date(invoice.issued_at).toLocaleDateString()}</>
            ) : null}
            {invoice.due_at ? (
              <> · due {new Date(invoice.due_at).toLocaleDateString()}</>
            ) : null}
          </p>
        </div>
        <div className="flex gap-2">
          {isDraft && canWrite ? (
            <Button asChild variant="outline">
              <Link to={`/invoices/${invoice.id}/edit`}>Edit</Link>
            </Button>
          ) : null}
          <Button variant="outline" onClick={openPdf} data-testid="invoice-pdf">
            Download PDF
          </Button>
          <Button variant="outline" asChild>
            <Link to="/invoices">Back</Link>
          </Button>
        </div>
      </header>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {canWrite ? (
        <div className="flex flex-wrap gap-2" data-testid="invoice-actions">
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
              onClick={() => void voidInvoice()}
              data-testid="action-void"
            >
              Void
            </Button>
          ) : null}
          {canRecordPayment ? (
            <Button
              variant="secondary"
              onClick={() =>
                navigate(`/payments/new?invoice_id=${invoice.id}`)
              }
              data-testid="action-record-payment"
            >
              Record payment
            </Button>
          ) : null}
          {canIssueNotes ? (
            <>
              <Button
                variant="outline"
                onClick={() =>
                  setInline(inline === "credit" ? "none" : "credit")
                }
                data-testid="action-credit-note"
              >
                Issue credit note
              </Button>
              <Button
                variant="outline"
                onClick={() =>
                  setInline(inline === "debit" ? "none" : "debit")
                }
                data-testid="action-debit-note"
              >
                Issue debit note
              </Button>
            </>
          ) : null}
        </div>
      ) : null}

      {inline === "credit" ? (
        <CreditNoteComposer
          invoiceId={invoice.id}
          onClose={() => setInline("none")}
          onIssued={() => {
            setInline("none");
            void refetchNotes();
            void refetch();
          }}
        />
      ) : null}
      {inline === "debit" ? (
        <DebitNoteComposer
          invoiceId={invoice.id}
          onClose={() => setInline("none")}
          onIssued={() => {
            setInline("none");
            void refetchNotes();
            void refetch();
          }}
        />
      ) : null}

      <div className="rounded-lg border border-border p-4">
        <h2 className="text-sm font-semibold">Lines</h2>
        <table className="mt-2 w-full table-fixed border-collapse text-sm">
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
            {(invoice.items ?? []).map((it) => (
              <tr key={it.id} className="border-b border-border/50">
                <td className="py-2 pr-2 font-mono text-xs">{it.line_number}</td>
                <td className="py-2 pr-2">{it.kind}</td>
                <td className="py-2 pr-2">{it.description}</td>
                <td className="py-2 pr-2 text-right font-mono">{it.quantity}</td>
                <td className="py-2 pr-2 text-right font-mono">${it.unit_price}</td>
                <td className="py-2 pr-2 text-right font-mono">
                  ${it.extended_amount}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-lg border border-border p-4 text-sm">
          <h2 className="font-semibold">Totals</h2>
          <dl className="mt-2 grid grid-cols-2 gap-y-1">
            <dt className="text-muted-foreground">Subtotal</dt>
            <dd className="text-right font-mono">${invoice.subtotal}</dd>
            <dt className="text-muted-foreground">Discount</dt>
            <dd className="text-right font-mono">−${invoice.discount_amount}</dd>
            <dt className="text-muted-foreground">Tax</dt>
            <dd className="text-right font-mono">${invoice.tax_amount}</dd>
            <dt className="font-semibold">Total</dt>
            <dd className="text-right font-mono font-semibold">
              ${invoice.total_amount}
            </dd>
            <dt className="text-muted-foreground">Paid</dt>
            <dd className="text-right font-mono">${invoice.amount_paid}</dd>
            <dt className="font-semibold">Outstanding</dt>
            <dd className="text-right font-mono font-semibold">
              ${invoice.amount_outstanding}
            </dd>
          </dl>
        </div>
        <div className="rounded-lg border border-border p-4 text-sm">
          <h2 className="font-semibold">History</h2>
          {creditNotes.length === 0 && debitNotes.length === 0 ? (
            <p className="mt-1 text-xs text-muted-foreground">
              No credit or debit notes.
            </p>
          ) : (
            <ul className="mt-2 space-y-1 text-xs">
              {creditNotes.map((cn) => (
                <li
                  key={cn.id}
                  className="flex justify-between border-b border-border/50 py-1"
                  data-testid={`credit-note-${cn.id}`}
                >
                  <span>Credit · {cn.credit_note_number}</span>
                  <span>{cn.state}</span>
                  <span className="font-mono">−${cn.total_amount}</span>
                </li>
              ))}
              {debitNotes.map((dn) => (
                <li
                  key={dn.id}
                  className="flex justify-between border-b border-border/50 py-1"
                  data-testid={`debit-note-${dn.id}`}
                >
                  <span>Debit · {dn.debit_note_number}</span>
                  <span>{dn.state}</span>
                  <span className="font-mono">${dn.total_amount}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <IssueInvoiceModal
        open={issueOpen}
        onOpenChange={setIssueOpen}
        invoice={invoice}
        onConfirm={issueConfirm}
        busy={busy}
      />
    </section>
  );
}
