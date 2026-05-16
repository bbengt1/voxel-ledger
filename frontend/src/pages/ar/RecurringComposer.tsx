/**
 * `/recurring-invoices/new` and `/recurring-invoices/:id/edit` — composer
 * for recurring invoice templates. Mirrors the InvoiceComposer with a
 * cadence panel and a "next will issue on X" preview computed from
 * cadence kind + interval + start date.
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

type RecurringTemplateResponse = components["schemas"]["RecurringTemplateResponse"];
type RecurringTemplateCreate = components["schemas"]["RecurringTemplateCreate"];
type RecurringTemplateUpdate = components["schemas"]["RecurringTemplateUpdate"];
type RecurringTemplateItemCreate = components["schemas"]["RecurringTemplateItemCreate"];

type CadenceKind = "daily" | "weekly" | "monthly" | "quarterly" | "yearly";

const CADENCES: readonly CadenceKind[] = [
  "daily",
  "weekly",
  "monthly",
  "quarterly",
  "yearly",
];

/** Compute the next issue date for preview purposes only. The server is
 * the source of truth — this is a UX hint. */
function previewNextIssue(
  startIso: string,
  kind: CadenceKind,
  interval: number,
): Date | null {
  if (!startIso) return null;
  const d = new Date(startIso);
  if (Number.isNaN(d.getTime())) return null;
  const i = Math.max(1, Math.floor(interval || 1));
  if (kind === "daily") d.setDate(d.getDate() + i);
  else if (kind === "weekly") d.setDate(d.getDate() + 7 * i);
  else if (kind === "monthly") d.setMonth(d.getMonth() + i);
  else if (kind === "quarterly") d.setMonth(d.getMonth() + 3 * i);
  else if (kind === "yearly") d.setFullYear(d.getFullYear() + i);
  return d;
}

export function RecurringComposerPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);

  const [customer, setCustomer] = useState<CustomerOption | null>(null);
  const [name, setName] = useState("");
  const [cadenceKind, setCadenceKind] = useState<CadenceKind>("monthly");
  const [cadenceInterval, setCadenceInterval] = useState("1");
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [autoIssue, setAutoIssue] = useState(false);
  const [discount, setDiscount] = useState("0");
  const [tax, setTax] = useState("0");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<LineDraft[]>(() => [emptyLine()]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api
      .get(
        `/api/v1/recurring-invoices/${id}` as "/api/v1/recurring-invoices/{template_id}",
      )
      .then((res) => {
        const t = res.data as unknown as RecurringTemplateResponse;
        setCustomer({ id: t.customer_id, label: t.customer_id.slice(0, 8) });
        setName(t.name);
        setCadenceKind(t.cadence_kind);
        setCadenceInterval(String(t.cadence_interval));
        setStartAt(t.start_at ? t.start_at.slice(0, 10) : "");
        setEndAt(t.end_at ? t.end_at.slice(0, 10) : "");
        setAutoIssue(t.auto_issue);
        setDiscount(t.discount_amount);
        setTax(t.tax_amount);
        setNotes(t.notes ?? "");
        const items = t.items ?? [];
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
            `/api/v1/customers/${t.customer_id}` as "/api/v1/customers/{customer_id}",
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
      .catch(() => setError("Could not load recurring template."));
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

  const nextIssuePreview = useMemo(
    () =>
      previewNextIssue(
        startAt,
        cadenceKind,
        Number.parseInt(cadenceInterval, 10) || 1,
      ),
    [startAt, cadenceKind, cadenceInterval],
  );

  function buildItems(): RecurringTemplateItemCreate[] {
    const out: RecurringTemplateItemCreate[] = [];
    for (const l of lines) {
      if (!l.description.trim()) continue;
      const item: RecurringTemplateItemCreate = {
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
    if (!name.trim()) {
      setError("Give the template a name.");
      return;
    }
    if (!startAt) {
      setError("Pick a start date.");
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
      let templateId: string;
      const intervalNum = Math.max(
        1,
        Number.parseInt(cadenceInterval, 10) || 1,
      );
      if (isEdit && id) {
        const body: RecurringTemplateUpdate = {
          name: name.trim(),
          cadence_kind: cadenceKind,
          cadence_interval: intervalNum,
          start_at: new Date(startAt).toISOString(),
          end_at: endAt ? new Date(endAt).toISOString() : null,
          auto_issue: autoIssue,
          discount_amount: discount,
          tax_amount: tax,
          notes: notes.trim() || null,
          items,
        };
        await apiClient.patch(`/api/v1/recurring-invoices/${id}`, body);
        templateId = id;
      } else {
        const body: RecurringTemplateCreate = {
          customer_id: customer.id,
          name: name.trim(),
          cadence_kind: cadenceKind,
          cadence_interval: intervalNum,
          start_at: new Date(startAt).toISOString(),
          auto_issue: autoIssue,
          currency: "USD",
          discount_amount: discount,
          tax_amount: tax,
          items,
        };
        if (endAt) body.end_at = new Date(endAt).toISOString();
        if (notes.trim()) body.notes = notes.trim();
        const res = await apiClient.post<RecurringTemplateResponse>(
          "/api/v1/recurring-invoices",
          body,
        );
        templateId = res.data.id;
      }
      navigate(`/recurring-invoices/${templateId}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : "Could not save template.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="flex gap-6">
      <div className="flex-1 space-y-6">
        <header>
          <h1 className="text-xl font-semibold">
            {isEdit ? "Edit recurring invoice" : "New recurring invoice"}
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
                disabled={isEdit}
                data-testid="recurring-customer-picker"
              />
            </label>
            <label className="block text-sm">
              Name
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                data-testid="recurring-name"
              />
            </label>
          </div>
        </div>

        <div className="space-y-3 rounded-lg border border-border p-4">
          <h2 className="text-sm font-semibold">Cadence</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <label className="block text-sm">
              Kind
              <select
                className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                value={cadenceKind}
                onChange={(e) =>
                  setCadenceKind(e.target.value as CadenceKind)
                }
                data-testid="recurring-cadence-kind"
              >
                {CADENCES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              Every
              <Input
                type="number"
                min={1}
                value={cadenceInterval}
                onChange={(e) => setCadenceInterval(e.target.value)}
                data-testid="recurring-cadence-interval"
              />
            </label>
            <label className="block text-sm">
              Start
              <Input
                type="date"
                value={startAt}
                onChange={(e) => setStartAt(e.target.value)}
                data-testid="recurring-start-at"
              />
            </label>
            <label className="block text-sm">
              End (optional)
              <Input
                type="date"
                value={endAt}
                onChange={(e) => setEndAt(e.target.value)}
                data-testid="recurring-end-at"
              />
            </label>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={autoIssue}
              onChange={(e) => setAutoIssue(e.target.checked)}
              data-testid="recurring-auto-issue"
            />
            Auto-issue (otherwise drafts are created)
          </label>
          <p
            className="text-xs text-muted-foreground"
            data-testid="recurring-next-preview"
          >
            {nextIssuePreview
              ? `Next will issue on ${nextIssuePreview.toLocaleDateString()}.`
              : "Pick a start date to preview the next issue."}
          </p>
        </div>

        <div className="space-y-3 rounded-lg border border-border p-4">
          <h2 className="text-sm font-semibold">Totals overrides</h2>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              Discount
              <Input
                type="number"
                step="0.01"
                value={discount}
                onChange={(e) => setDiscount(e.target.value)}
                data-testid="recurring-discount"
              />
            </label>
            <label className="block text-sm">
              Tax
              <Input
                type="number"
                step="0.01"
                value={tax}
                onChange={(e) => setTax(e.target.value)}
                data-testid="recurring-tax"
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
              data-testid="recurring-notes"
            />
          </label>
        </div>

        <LineItemTable
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
            data-testid="save-recurring-btn"
          >
            {submitting ? "Saving…" : "Save template"}
          </Button>
          <Button
            variant="outline"
            disabled={submitting}
            onClick={() => navigate("/recurring-invoices")}
          >
            Cancel
          </Button>
        </div>
      </div>

      <InvoiceTotalsPanel totals={totals} />
    </section>
  );
}
