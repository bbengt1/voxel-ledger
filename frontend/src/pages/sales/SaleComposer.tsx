/**
 * `/sales/new` and `/sales/:id` for drafts — sale composer.
 *
 * Layout: header form + dynamic line table on the left, sticky totals
 * panel on the right. Each line is one of product / job / manual, and
 * picking a product or completed job auto-fills description + unit_price.
 *
 * Save draft → POST /api/v1/sales (or PATCH on edit).
 * Save + confirm → POST sale, then POST /api/v1/sales/{id}/confirm.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import {
  EntityPicker,
  type EntityOption,
} from "@/components/inventory/EntityPicker";
import { SaleTotalsPanel } from "@/components/sales/SaleTotalsPanel";
import { computeTotals } from "@/components/sales/totals";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type SaleResponse = components["schemas"]["SaleResponse"];
type SalesChannelResponse = components["schemas"]["SalesChannelResponse"];
type SaleItemCreate = components["schemas"]["SaleItemCreate"];
type SaleCreate = components["schemas"]["SaleCreate"];
type SaleUpdate = components["schemas"]["SaleUpdate"];
type JobResponse = components["schemas"]["JobResponse"];
type LineKind = SaleItemCreate["kind"];

let _key = 0;
const nextKey = () => `sl${++_key}`;

interface LineDraft {
  key: string;
  kind: LineKind;
  product: EntityOption | null;
  jobId: string;
  description: string;
  quantity: string;
  unitPrice: string;
  skuOrJobNumber: string;
}

function emptyLine(): LineDraft {
  return {
    key: nextKey(),
    kind: "manual",
    product: null,
    jobId: "",
    description: "",
    quantity: "1",
    unitPrice: "",
    skuOrJobNumber: "",
  };
}

function num(v: string): number {
  const n = Number.parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

export function SaleComposerPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);

  const [channels, setChannels] = useState<SalesChannelResponse[]>([]);
  const [channelId, setChannelId] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [occurredAt, setOccurredAt] = useState(() =>
    new Date().toISOString().slice(0, 16),
  );
  const [discount, setDiscount] = useState("0");
  const [shipping, setShipping] = useState("0");
  const [tax, setTax] = useState("0");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<LineDraft[]>(() => [emptyLine()]);
  const [completedJobs, setCompletedJobs] = useState<JobResponse[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get("/api/v1/sales-channels", { params: { active: "true" } })
      .then((res) => setChannels(res.data.items))
      .catch(() => {
        /* non-fatal */
      });
  }, []);

  useEffect(() => {
    api
      .get("/api/v1/jobs", { params: { state: "completed" } })
      .then((res) => setCompletedJobs(res.data.items))
      .catch(() => {
        /* non-fatal */
      });
  }, []);

  // Hydrate draft on edit.
  useEffect(() => {
    if (!id) return;
    api
      .get(`/api/v1/sales/${id}` as "/api/v1/sales/{sale_id}")
      .then((res) => {
        const sale = res.data as unknown as SaleResponse;
        setChannelId(sale.channel_id);
        setCustomerName(sale.customer_name);
        setCustomerEmail(sale.customer_email ?? "");
        setOccurredAt(sale.occurred_at.slice(0, 16));
        setDiscount(sale.discount_amount);
        setShipping(sale.shipping_amount);
        setTax(sale.tax_amount);
        setNotes(sale.notes ?? "");
        const items = sale.items ?? [];
        if (items.length > 0) {
          setLines(
            items.map((it) => ({
              key: nextKey(),
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
      })
      .catch(() => {
        setError("Could not load draft.");
      });
  }, [id]);

  const selectedChannel = useMemo(
    () => channels.find((c) => c.id === channelId) ?? null,
    [channels, channelId],
  );

  const lineExtended = useMemo(
    () => lines.map((l) => num(l.quantity) * num(l.unitPrice)),
    [lines],
  );

  const totals = useMemo(
    () =>
      computeTotals({
        lineExtended,
        discount: num(discount),
        shipping: num(shipping),
        tax: num(tax),
        channel: selectedChannel,
      }),
    [lineExtended, discount, shipping, tax, selectedChannel],
  );

  function updateLine(idx: number, patch: Partial<LineDraft>) {
    setLines((prev) =>
      prev.map((l, i) => (i === idx ? { ...l, ...patch } : l)),
    );
  }

  const onPickProduct = useCallback(
    async (idx: number, opt: EntityOption | null) => {
      updateLine(idx, { product: opt });
      if (!opt) return;
      try {
        const res = await api.get(
          `/api/v1/products/${opt.id}` as "/api/v1/products/{product_id}",
        );
        const p = res.data as unknown as {
          name: string;
          sku?: string | null;
          unit_price: string;
        };
        updateLine(idx, {
          description: p.name,
          unitPrice: p.unit_price,
          skuOrJobNumber: p.sku ?? "",
        });
      } catch {
        /* leave description blank — user can override */
      }
    },
    [],
  );

  function onPickJob(idx: number, jobId: string) {
    const job = completedJobs.find((j) => j.id === jobId);
    if (!job) {
      updateLine(idx, { jobId });
      return;
    }
    updateLine(idx, {
      jobId,
      description: `Job ${job.job_number}`,
      skuOrJobNumber: job.job_number,
    });
  }

  function buildItems(): SaleItemCreate[] {
    const out: SaleItemCreate[] = [];
    for (const l of lines) {
      if (!l.description.trim()) continue;
      const item: SaleItemCreate = {
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

  async function submit(alsoConfirm: boolean) {
    if (!channelId) {
      setError("Pick a channel.");
      return;
    }
    if (!customerName.trim()) {
      setError("Customer name is required.");
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
      let saleId: string;
      if (isEdit && id) {
        const body: SaleUpdate = {
          channel_id: channelId,
          customer_name: customerName,
          customer_email: customerEmail.trim() || null,
          occurred_at: new Date(occurredAt).toISOString(),
          discount_amount: discount,
          shipping_amount: shipping,
          tax_amount: tax,
          notes: notes.trim() || null,
          items,
        };
        await apiClient.patch(`/api/v1/sales/${id}`, body);
        saleId = id;
      } else {
        const body: SaleCreate = {
          channel_id: channelId,
          customer_name: customerName,
          occurred_at: new Date(occurredAt).toISOString(),
          discount_amount: discount,
          shipping_amount: shipping,
          tax_amount: tax,
          items,
        };
        if (customerEmail.trim()) body.customer_email = customerEmail.trim();
        if (notes.trim()) body.notes = notes.trim();
        const res = await apiClient.post<SaleResponse>(
          "/api/v1/sales",
          body,
        );
        saleId = res.data.id;
      }

      if (alsoConfirm) {
        await apiClient.post(`/api/v1/sales/${saleId}/confirm`);
      }
      navigate(`/sales/${saleId}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not save sale.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="flex gap-6">
      <div className="flex-1 space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-xl font-semibold">
            {isEdit ? "Edit sale" : "New sale"}
          </h1>
        </header>

        <div className="space-y-3 rounded-lg border border-border p-4">
          <h2 className="text-sm font-semibold">Header</h2>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              Channel
              <select
                className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                value={channelId}
                onChange={(e) => setChannelId(e.target.value)}
                data-testid="sale-channel"
              >
                <option value="">— Pick a channel —</option>
                {channels.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              Occurred at
              <Input
                type="datetime-local"
                value={occurredAt}
                onChange={(e) => setOccurredAt(e.target.value)}
                data-testid="sale-occurred-at"
              />
            </label>
            <label className="block text-sm">
              Customer name
              <Input
                value={customerName}
                onChange={(e) => setCustomerName(e.target.value)}
                data-testid="sale-customer-name"
              />
            </label>
            <label className="block text-sm">
              Customer email
              <Input
                type="email"
                value={customerEmail}
                onChange={(e) => setCustomerEmail(e.target.value)}
                data-testid="sale-customer-email"
              />
            </label>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <label className="block text-sm">
              Discount
              <Input
                type="number"
                step="0.01"
                value={discount}
                onChange={(e) => setDiscount(e.target.value)}
                data-testid="sale-discount"
              />
            </label>
            <label className="block text-sm">
              Shipping
              <Input
                type="number"
                step="0.01"
                value={shipping}
                onChange={(e) => setShipping(e.target.value)}
                data-testid="sale-shipping"
              />
            </label>
            <label className="block text-sm">
              Tax
              <Input
                type="number"
                step="0.01"
                value={tax}
                onChange={(e) => setTax(e.target.value)}
                data-testid="sale-tax"
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
              data-testid="sale-notes"
            />
          </label>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">Lines</h2>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setLines((p) => [...p, emptyLine()])}
              data-testid="add-line-btn"
            >
              Add line
            </Button>
          </div>

          {lines.map((line, idx) => (
            <div
              key={line.key}
              className="space-y-2 rounded-lg border border-border p-3"
              data-testid={`line-row-${idx}`}
            >
              <div className="flex items-center justify-between">
                <select
                  className="h-8 rounded-md border border-input bg-background px-2 text-xs"
                  value={line.kind}
                  onChange={(e) =>
                    updateLine(idx, {
                      kind: e.target.value as LineKind,
                      product: null,
                      jobId: "",
                    })
                  }
                  data-testid={`line-${idx}-kind`}
                >
                  <option value="manual">Manual</option>
                  <option value="product">Product</option>
                  <option value="job">Job</option>
                </select>
                {lines.length > 1 ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() =>
                      setLines((prev) => prev.filter((_, i) => i !== idx))
                    }
                    data-testid={`remove-line-${idx}`}
                  >
                    ×
                  </Button>
                ) : null}
              </div>

              {line.kind === "product" ? (
                <EntityPicker
                  kind="product"
                  value={line.product}
                  onChange={(opt) => void onPickProduct(idx, opt)}
                  data-testid={`line-${idx}-product-picker`}
                />
              ) : line.kind === "job" ? (
                <select
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                  value={line.jobId}
                  onChange={(e) => onPickJob(idx, e.target.value)}
                  data-testid={`line-${idx}-job-picker`}
                >
                  <option value="">— Pick completed job —</option>
                  {completedJobs.map((j) => (
                    <option key={j.id} value={j.id}>
                      {j.job_number} ({j.pieces_produced} pcs)
                    </option>
                  ))}
                </select>
              ) : null}

              <Input
                value={line.description}
                placeholder="Description"
                onChange={(e) =>
                  updateLine(idx, { description: e.target.value })
                }
                data-testid={`line-${idx}-description`}
              />
              <div className="grid grid-cols-3 gap-2">
                <Input
                  type="number"
                  min={0}
                  step="0.01"
                  value={line.quantity}
                  onChange={(e) =>
                    updateLine(idx, { quantity: e.target.value })
                  }
                  placeholder="Qty"
                  data-testid={`line-${idx}-quantity`}
                />
                <Input
                  type="number"
                  min={0}
                  step="0.01"
                  value={line.unitPrice}
                  onChange={(e) =>
                    updateLine(idx, { unitPrice: e.target.value })
                  }
                  placeholder="Unit price"
                  data-testid={`line-${idx}-unit-price`}
                />
                <div
                  className="flex items-center justify-end pr-2 text-sm font-mono text-muted-foreground"
                  data-testid={`line-${idx}-extended`}
                >
                  ${(lineExtended[idx] ?? 0).toFixed(2)}
                </div>
              </div>
            </div>
          ))}
        </div>

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
            type="button"
            disabled={submitting}
            onClick={() => void submit(false)}
            data-testid="save-draft-btn"
          >
            {submitting ? "Saving…" : "Save draft"}
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={submitting}
            onClick={() => void submit(true)}
            data-testid="save-confirm-btn"
          >
            Save + confirm
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={submitting}
            onClick={() => navigate("/sales")}
          >
            Cancel
          </Button>
        </div>
      </div>

      <SaleTotalsPanel totals={totals} channel={selectedChannel} />
    </section>
  );
}
