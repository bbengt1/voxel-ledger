/**
 * `/invoices/new` and `/invoices/:id` (drafts only) — invoice composer.
 * Identical UX to the quote composer with a `due_at` field instead of
 * `valid_until`. Tax is operator-supplied.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PullBillableExpensesModal } from "@/components/ap/PullBillableExpensesModal";
import {
  CustomerPicker,
  type CustomerOption,
} from "@/components/ar/CustomerPicker";
import { InvoiceTotalsPanel } from "@/components/ar/InvoiceTotalsPanel";
import {
  LineItemTable,
  emptyLine,
  lineNum,
  type LineDraft,
} from "@/components/ar/LineItemTable";
import { computeArTotals } from "@/components/ar/totals";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type InvoiceResponse = components["schemas"]["InvoiceResponse"];
type InvoiceCreate = components["schemas"]["InvoiceCreate"];
type InvoiceUpdate = components["schemas"]["InvoiceUpdate"];
type InvoiceItemCreate = components["schemas"]["InvoiceItemCreate"];

export function InvoiceComposerPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);

  const [customer, setCustomer] = useState<CustomerOption | null>(null);
  const [dueAt, setDueAt] = useState("");
  const [discount, setDiscount] = useState("0");
  const [tax, setTax] = useState("0");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<LineDraft[]>(() => [emptyLine()]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pullOpen, setPullOpen] = useState(false);

  useEffect(() => {
    if (!id) return;
    api
      .get(`/api/v1/invoices/${id}` as "/api/v1/invoices/{invoice_id}")
      .then((res) => {
        const inv = res.data as unknown as InvoiceResponse;
        setCustomer({ id: inv.customer_id, label: inv.customer_id.slice(0, 8) });
        setDueAt(inv.due_at ? inv.due_at.slice(0, 10) : "");
        setDiscount(inv.discount_amount);
        setTax(inv.tax_amount);
        setNotes(inv.notes ?? "");
        const items = inv.items ?? [];
        if (items.length > 0) {
          setLines(
            items.map((it) => ({
              key: `existing-${it.id}`,
              kind: it.kind,
              product: it.product_id
                ? { id: it.product_id, label: it.description }
                : null,
              jobId: it.job_id ?? "",
              description: it.description,
              quantity: it.quantity,
              unitPrice: it.unit_price,
              skuOrJobNumber: it.sku_or_job_number ?? "",
            })),
          );
        }
        api
          .get(
            `/api/v1/customers/${inv.customer_id}` as "/api/v1/customers/{customer_id}",
          )
          .then((cres) => {
            const c = cres.data as unknown as {
              id: string;
              display_name: string;
              customer_number: string;
            };
            setCustomer({
              id: c.id,
              label: `${c.display_name} (${c.customer_number})`,
            });
          })
          .catch(() => {
            /* fall back to id slice */
          });
      })
      .catch(() => setError("Could not load invoice draft."));
  }, [id]);

  const lineExtended = useMemo(
    () => lines.map((l) => lineNum(l.quantity) * lineNum(l.unitPrice)),
    [lines],
  );

  const totals = useMemo(
    () =>
      computeArTotals({
        lineExtended,
        discount: lineNum(discount),
        tax: lineNum(tax),
      }),
    [lineExtended, discount, tax],
  );

  function buildItems(): InvoiceItemCreate[] {
    const out: InvoiceItemCreate[] = [];
    for (const l of lines) {
      if (!l.description.trim()) continue;
      const item: InvoiceItemCreate = {
        kind: l.kind,
        description: l.description,
        quantity: l.quantity || "1",
        unit_price: l.unitPrice || "0",
      };
      if (l.skuOrJobNumber) item.sku_or_job_number = l.skuOrJobNumber;
      if (l.kind === "product" && l.product) item.product_id = l.product.id;
      if (l.kind === "job" && l.jobId) item.job_id = l.jobId;
      if (l.billableSource) {
        item.billable_source = {
          kind: l.billableSource.kind,
          id: l.billableSource.id,
        };
      }
      out.push(item);
    }
    return out;
  }

  async function submit() {
    if (!customer) {
      setError("Pick a customer.");
      return;
    }
    const items = buildItems();
    if (items.length === 0) {
      setError("Add at least one line with a description.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      let invoiceId: string;
      if (isEdit && id) {
        const body: InvoiceUpdate = {
          customer_id: customer.id,
          due_at: dueAt || null,
          discount_amount: discount,
          tax_amount: tax,
          notes: notes.trim() || null,
          items,
        };
        await apiClient.patch(`/api/v1/invoices/${id}`, body);
        invoiceId = id;
      } else {
        const body: InvoiceCreate = {
          customer_id: customer.id,
          currency: "USD",
          discount_amount: discount,
          tax_amount: tax,
          items,
        };
        if (dueAt) body.due_at = dueAt;
        if (notes.trim()) body.notes = notes.trim();
        const res = await apiClient.post<InvoiceResponse>(
          "/api/v1/invoices",
          body,
        );
        invoiceId = res.data.id;
      }
      navigate(`/invoices/${invoiceId}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not save invoice.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="flex gap-6">
      <div className="flex-1 space-y-6">
        <header>
          <h1 className="text-xl font-semibold">
            {isEdit ? "Edit invoice" : "New invoice"}
          </h1>
        </header>

        <div className="space-y-3 rounded-lg border border-border p-4">
          <h2 className="text-sm font-semibold">Header</h2>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              Customer
              <CustomerPicker
                value={customer}
                onChange={setCustomer}
                data-testid="invoice-customer-picker"
              />
            </label>
            <label className="block text-sm">
              Due at
              <Input
                type="date"
                value={dueAt}
                onChange={(e) => setDueAt(e.target.value)}
                data-testid="invoice-due-at"
              />
            </label>
            <label className="block text-sm">
              Discount
              <Input
                type="number"
                step="0.01"
                value={discount}
                onChange={(e) => setDiscount(e.target.value)}
                data-testid="invoice-discount"
              />
            </label>
            <label className="block text-sm">
              Tax
              <Input
                type="number"
                step="0.01"
                value={tax}
                onChange={(e) => setTax(e.target.value)}
                data-testid="invoice-tax"
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
              data-testid="invoice-notes"
            />
          </label>
        </div>

        {customer ? (
          <div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setPullOpen(true)}
              data-testid="pull-billable-btn"
            >
              Pull billable expenses
            </Button>
          </div>
        ) : null}

        <LineItemTable
          lines={lines}
          setLines={setLines}
          lineExtended={lineExtended}
        />

        {error ? (
          <p role="alert" data-testid="composer-error" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <div className="flex gap-2">
          <Button
            disabled={submitting}
            onClick={() => void submit()}
            data-testid="save-draft-btn"
          >
            {submitting ? "Saving…" : "Save draft"}
          </Button>
          <Button
            variant="outline"
            disabled={submitting}
            onClick={() => navigate("/invoices")}
          >
            Cancel
          </Button>
        </div>
      </div>

      <InvoiceTotalsPanel totals={totals} />

      {customer ? (
        <PullBillableExpensesModal
          open={pullOpen}
          onOpenChange={setPullOpen}
          customerId={customer.id}
          onConfirm={(rows) => {
            if (rows.length === 0) return;
            setLines((prev) => {
              const next = prev.filter((l) => l.description.trim().length > 0);
              for (const r of rows) {
                next.push({
                  key: `bill-${r.source_kind}-${r.source_id}`,
                  kind: "manual",
                  product: null,
                  jobId: "",
                  description: r.description,
                  quantity: "1",
                  unitPrice: r.amount,
                  skuOrJobNumber: "",
                  billableSource: { kind: r.source_kind, id: r.source_id },
                });
              }
              return next.length === 0 ? prev : next;
            });
          }}
        />
      ) : null}
    </section>
  );
}
