/**
 * `/quotes/new` and `/quotes/:id` (drafts only) — quote composer. Mirrors
 * the SaleComposer pattern. Tax + discount are operator-supplied.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
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

type QuoteResponse = components["schemas"]["QuoteResponse"];
type QuoteCreate = components["schemas"]["QuoteCreate"];
type QuoteUpdate = components["schemas"]["QuoteUpdate"];
type QuoteItemCreate = components["schemas"]["QuoteItemCreate"];

export function QuoteComposerPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);

  const [customer, setCustomer] = useState<CustomerOption | null>(null);
  const [validUntil, setValidUntil] = useState("");
  const [discount, setDiscount] = useState("0");
  const [tax, setTax] = useState("0");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<LineDraft[]>(() => [emptyLine()]);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api
      .get(`/api/v1/quotes/${id}` as "/api/v1/quotes/{quote_id}")
      .then((res) => {
        const q = res.data as unknown as QuoteResponse;
        setCustomer({ id: q.customer_id, label: q.customer_id.slice(0, 8) });
        setValidUntil(q.valid_until ? q.valid_until.slice(0, 10) : "");
        setDiscount(q.discount_amount);
        setTax(q.tax_amount);
        setNotes(q.notes ?? "");
        const items = q.items ?? [];
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
        // Refetch customer label for display.
        api
          .get(
            `/api/v1/customers/${q.customer_id}` as "/api/v1/customers/{customer_id}",
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
            /* keep id-slice fallback */
          });
      })
      .catch(() => setError("Could not load quote draft."));
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

  function buildItems(): QuoteItemCreate[] {
    const out: QuoteItemCreate[] = [];
    for (const l of lines) {
      if (!l.description.trim()) continue;
      const item: QuoteItemCreate = {
        kind: l.kind,
        description: l.description,
        quantity: l.quantity || "1",
        unit_price: l.unitPrice || "0",
      };
      if (l.skuOrJobNumber) item.sku_or_job_number = l.skuOrJobNumber;
      if (l.kind === "product" && l.product) item.product_id = l.product.id;
      if (l.kind === "job" && l.jobId) item.job_id = l.jobId;
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
      let quoteId: string;
      if (isEdit && id) {
        const body: QuoteUpdate = {
          customer_id: customer.id,
          valid_until: validUntil || null,
          discount_amount: discount,
          tax_amount: tax,
          notes: notes.trim() || null,
          items,
        };
        await apiClient.patch(`/api/v1/quotes/${id}`, body);
        quoteId = id;
      } else {
        const body: QuoteCreate = {
          customer_id: customer.id,
          discount_amount: discount,
          tax_amount: tax,
          items,
        };
        if (validUntil) body.valid_until = validUntil;
        if (notes.trim()) body.notes = notes.trim();
        const res = await apiClient.post<QuoteResponse>(
          "/api/v1/quotes",
          body,
        );
        quoteId = res.data.id;
      }
      navigate(`/quotes/${quoteId}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not save quote.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="flex gap-6">
      <div className="flex-1 space-y-6">
        <header>
          <h1 className="text-xl font-semibold">
            {isEdit ? "Edit quote" : "New quote"}
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
                data-testid="quote-customer-picker"
              />
            </label>
            <label className="block text-sm">
              Valid until
              <Input
                type="date"
                value={validUntil}
                onChange={(e) => setValidUntil(e.target.value)}
                data-testid="quote-valid-until"
              />
            </label>
            <label className="block text-sm">
              Discount
              <Input
                type="number"
                step="0.01"
                value={discount}
                onChange={(e) => setDiscount(e.target.value)}
                data-testid="quote-discount"
              />
            </label>
            <label className="block text-sm">
              Tax
              <Input
                type="number"
                step="0.01"
                value={tax}
                onChange={(e) => setTax(e.target.value)}
                data-testid="quote-tax"
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
              data-testid="quote-notes"
            />
          </label>
        </div>

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
            onClick={() => navigate("/quotes")}
          >
            Cancel
          </Button>
        </div>
      </div>

      <InvoiceTotalsPanel totals={totals} />
    </section>
  );
}
