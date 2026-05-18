/**
 * `/bills/new` and `/bills/:id/edit` (drafts only) — bill composer.
 * Header form (vendor picker, vendor_invoice_number, due_at, discount,
 * tax, notes) + dynamic line table with `manual` / `expense_category`
 * line kinds and per-line expense account overrides. Save-draft on top
 * of POST /bills.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { BillTotalsPanel } from "@/components/ap/BillTotalsPanel";
import {
  BillLineTable,
  billLineNum,
  emptyBillLine,
  type BillLineDraft,
} from "@/components/ap/BillLineTable";
import { computeBillTotals } from "@/components/ap/totals";
import { VendorPicker, type VendorOption } from "@/components/ap/VendorPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type BillResponse = components["schemas"]["BillResponse"];
type BillCreate = components["schemas"]["BillCreate"];
type BillUpdate = components["schemas"]["BillUpdate"];
type BillItemCreate = components["schemas"]["BillItemCreate"];

export function BillComposerPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);

  const [vendor, setVendor] = useState<VendorOption | null>(null);
  const [vendorInvoiceNumber, setVendorInvoiceNumber] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [discount, setDiscount] = useState("0");
  const [tax, setTax] = useState("0");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<BillLineDraft[]>(() => [emptyBillLine()]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api
      .get(`/api/v1/bills/${id}` as "/api/v1/bills/{bill_id}")
      .then((res) => {
        const b = res.data as unknown as BillResponse;
        setVendor({ id: b.vendor_id, label: b.vendor_id.slice(0, 8) });
        setVendorInvoiceNumber(b.vendor_invoice_number ?? "");
        setDueAt(b.due_at ? b.due_at.slice(0, 10) : "");
        setDiscount(b.discount_amount);
        setTax(b.tax_amount);
        setNotes(b.notes ?? "");
        const items = b.items ?? [];
        if (items.length > 0) {
          setLines(
            items.map((it) => ({
              key: `existing-${it.id}`,
              kind: it.kind,
              expenseCategoryId: it.expense_category_id ?? "",
              description: it.description,
              quantity: it.quantity,
              unitPrice: it.unit_price,
              vendorSku: it.vendor_sku ?? "",
              expenseAccountIdOverride: it.expense_account_id_override ?? "",
            } satisfies BillLineDraft)),
          );
        }
        api
          .get(
            `/api/v1/vendors/${b.vendor_id}` as "/api/v1/vendors/{vendor_id}",
          )
          .then((vres) => {
            const v = vres.data as unknown as {
              id: string;
              display_name: string;
              vendor_number: string;
            };
            setVendor({
              id: v.id,
              label: `${v.display_name} (${v.vendor_number})`,
            });
          })
          .catch(() => {
            /* keep id-slice fallback */
          });
      })
      .catch(() => setError("Could not load bill draft."));
  }, [id]);

  const lineExtended = useMemo(
    () => lines.map((l) => billLineNum(l.quantity) * billLineNum(l.unitPrice)),
    [lines],
  );

  const totals = useMemo(
    () =>
      computeBillTotals({
        lineExtended,
        discount: billLineNum(discount),
        tax: billLineNum(tax),
      }),
    [lineExtended, discount, tax],
  );

  function buildItems(): BillItemCreate[] {
    const out: BillItemCreate[] = [];
    for (const l of lines) {
      if (!l.description.trim()) continue;
      const item: BillItemCreate = {
        kind: l.kind,
        description: l.description,
        quantity: l.quantity || "1",
        unit_price: l.unitPrice || "0",
      };
      if (l.kind === "expense_category" && l.expenseCategoryId) {
        item.expense_category_id = l.expenseCategoryId;
      }
      if (l.vendorSku.trim()) item.vendor_sku = l.vendorSku.trim();
      if (l.expenseAccountIdOverride) {
        item.expense_account_id_override = l.expenseAccountIdOverride;
      }
      out.push(item);
    }
    return out;
  }

  async function submit() {
    if (!vendor) {
      setError("Pick a vendor.");
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
      let billId: string;
      if (isEdit && id) {
        const body: BillUpdate = {
          vendor_id: vendor.id,
          vendor_invoice_number: vendorInvoiceNumber.trim() || null,
          due_at: dueAt || null,
          discount_amount: discount,
          tax_amount: tax,
          notes: notes.trim() || null,
          items,
        };
        await apiClient.patch(`/api/v1/bills/${id}`, body);
        billId = id;
      } else {
        const body: BillCreate = {
          vendor_id: vendor.id,
          currency: "USD",
          discount_amount: discount,
          tax_amount: tax,
          items,
        };
        if (vendorInvoiceNumber.trim()) {
          body.vendor_invoice_number = vendorInvoiceNumber.trim();
        }
        if (dueAt) body.due_at = dueAt;
        if (notes.trim()) body.notes = notes.trim();
        const res = await apiClient.post<BillResponse>("/api/v1/bills", body);
        billId = res.data.id;
      }
      navigate(`/bills/${billId}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not save bill.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="flex gap-6">
      <div className="flex-1 space-y-6">
        <header>
          <h1 className="text-xl font-semibold">
            {isEdit ? "Edit bill" : "New bill"}
          </h1>
        </header>

        <div className="space-y-3 rounded-lg border border-border p-4">
          <h2 className="text-sm font-semibold">Header</h2>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              Vendor
              <VendorPicker
                value={vendor}
                onChange={setVendor}
                data-testid="bill-vendor-picker"
              />
            </label>
            <label className="block text-sm">
              Vendor invoice #
              <Input
                value={vendorInvoiceNumber}
                onChange={(e) => setVendorInvoiceNumber(e.target.value)}
                data-testid="bill-vendor-invoice-number"
              />
            </label>
            <label className="block text-sm">
              Due at
              <Input
                type="date"
                value={dueAt}
                onChange={(e) => setDueAt(e.target.value)}
                data-testid="bill-due-at"
              />
            </label>
            <label className="block text-sm">
              Discount
              <Input
                type="number"
                step="0.01"
                value={discount}
                onChange={(e) => setDiscount(e.target.value)}
                data-testid="bill-discount"
              />
            </label>
            <label className="block text-sm">
              Tax
              <Input
                type="number"
                step="0.01"
                value={tax}
                onChange={(e) => setTax(e.target.value)}
                data-testid="bill-tax"
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
              data-testid="bill-notes"
            />
          </label>
        </div>

        <BillLineTable
          lines={lines}
          setLines={setLines}
          lineExtended={lineExtended}
        />

        {error ? (
          <p
            role="alert"
            data-testid="composer-error"
            className="text-sm text-destructive"
          >
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
            onClick={() => navigate("/bills")}
          >
            Cancel
          </Button>
        </div>
      </div>

      <BillTotalsPanel totals={totals} />
    </section>
  );
}
