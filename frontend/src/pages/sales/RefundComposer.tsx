/**
 * Refund composer (Phase 6.7b).
 *
 * Pulls the parent sale's line items, lets the cashier pick which
 * lines + quantities to refund, then submits to ``POST /api/v1/refunds``.
 *
 * The backend returns 201 if the refund is auto-approved (under
 * ``sales.refund.approval_threshold``) and 202 if it requires approval.
 * The 201/202 distinction is implicit in the ``RefundCreateResponse``:
 * ``approval_request_id`` is non-null iff the refund is pending
 * approval. We branch the redirect off that.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { AxiosError } from "axios";

import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/Button";
import type { components } from "@/api/types";

type SaleResponse = components["schemas"]["SaleResponse"];
type SettingResponse = components["schemas"]["SettingResponse"];
type RefundCreateResponse = components["schemas"]["RefundCreateResponse"];

const REASON_CODES = ["damaged", "wrong_item", "dispute", "other"] as const;
const THRESHOLD_KEY = "sales.refund.approval_threshold";
const DEFAULT_THRESHOLD = 500;

interface LineState {
  selected: boolean;
  quantity: string;
}

function extractDetail(err: unknown, fallback: string): string {
  const ax = err as AxiosError<{ detail?: string }>;
  return ax?.response?.data?.detail ?? fallback;
}

export function RefundComposerPage() {
  const { id: saleId = "" } = useParams();
  const navigate = useNavigate();
  const [sale, setSale] = useState<SaleResponse | null>(null);
  const [lines, setLines] = useState<Record<string, LineState>>({});
  const [reasonCode, setReasonCode] =
    useState<(typeof REASON_CODES)[number]>("damaged");
  const [restockInventory, setRestockInventory] = useState(true);
  const [notes, setNotes] = useState("");
  const [threshold, setThreshold] = useState<number>(DEFAULT_THRESHOLD);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!saleId) return;
    let cancelled = false;
    apiClient
      .get<SaleResponse>(`/api/v1/sales/${saleId}`)
      .then((res) => {
        if (cancelled) return;
        setSale(res.data);
        const items = res.data.items ?? [];
        const initial: Record<string, LineState> = {};
        for (const item of items) {
          initial[item.id] = { selected: false, quantity: item.quantity };
        }
        setLines(initial);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(extractDetail(err, "Failed to load sale."));
      });
    return () => {
      cancelled = true;
    };
  }, [saleId]);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<SettingResponse>(
        `/api/v1/settings/${encodeURIComponent(THRESHOLD_KEY)}`,
      )
      .then((res) => {
        if (cancelled) return;
        const raw = res.data.value as unknown;
        const parsed = Number(raw);
        if (Number.isFinite(parsed)) setThreshold(parsed);
      })
      .catch(() => {
        // Setting may be unset — stick with default.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const items = useMemo(() => sale?.items ?? [], [sale]);

  const total = useMemo(() => {
    let t = 0;
    for (const item of items) {
      const state = lines[item.id];
      if (!state?.selected) continue;
      const qty = Number(state.quantity);
      const unit = Number(item.unit_price);
      if (Number.isFinite(qty) && Number.isFinite(unit)) {
        t += qty * unit;
      }
    }
    return t;
  }, [items, lines]);

  const overThreshold = total > threshold;
  const selectedItems = items.filter((i) => lines[i.id]?.selected);

  async function submit() {
    if (!sale || selectedItems.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const payload = {
        sale_id: sale.id,
        kind: "partial" as const,
        reason_code: reasonCode,
        restock_inventory: restockInventory,
        notes: notes || null,
        items: selectedItems.map((item) => {
          // Non-null assertion safe — selectedItems is derived from `lines`.
          const state = lines[item.id] as LineState;
          return {
            sale_item_id: item.id,
            quantity: state.quantity,
            unit_amount: item.unit_price,
          };
        }),
      };
      const res = await apiClient.post<RefundCreateResponse>(
        "/api/v1/refunds",
        payload,
      );
      const body = res.data;
      if (body.approval_request_id) {
        // Over-threshold: routed to approvals queue.
        navigate(
          `/approvals?refund=${encodeURIComponent(body.refund.id)}&banner=refund-pending`,
        );
      } else {
        navigate(`/sales/refunds/${body.refund.id}`);
      }
    } catch (err) {
      setError(extractDetail(err, "Refund failed."));
    } finally {
      setBusy(false);
    }
  }

  if (!sale) {
    return (
      <section className="text-sm text-muted-foreground">
        {error ?? "Loading…"}
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          Refund for sale {sale.sale_number}
        </h1>
        <p className="text-sm text-muted-foreground">
          Customer: {sale.customer_name}
        </p>
      </header>

      {error && (
        <div role="alert" className="rounded border border-destructive p-3 text-sm">
          {error}
        </div>
      )}

      <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th></th>
            <th className="py-2">#</th>
            <th>Description</th>
            <th className="text-right">Sold qty</th>
            <th>Refund qty</th>
            <th className="text-right">Unit</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const state = lines[item.id] ?? { selected: false, quantity: "0" };
            return (
              <tr key={item.id} className="border-t border-border">
                <td>
                  <input
                    type="checkbox"
                    aria-label={`select line ${item.line_number}`}
                    data-testid={`line-checkbox-${item.line_number}`}
                    checked={state.selected}
                    onChange={(e) =>
                      setLines((p) => ({
                        ...p,
                        [item.id]: {
                          ...(p[item.id] ?? { quantity: item.quantity }),
                          selected: e.target.checked,
                        },
                      }))
                    }
                  />
                </td>
                <td className="py-2">{item.line_number}</td>
                <td>{item.description}</td>
                <td className="text-right">{item.quantity}</td>
                <td>
                  <input
                    type="text"
                    inputMode="decimal"
                    aria-label={`refund quantity for line ${item.line_number}`}
                    data-testid={`line-qty-${item.line_number}`}
                    value={state.quantity}
                    onChange={(e) =>
                      setLines((p) => ({
                        ...p,
                        [item.id]: {
                          ...(p[item.id] ?? { selected: false }),
                          quantity: e.target.value,
                        },
                      }))
                    }
                    className="h-8 w-20 rounded border border-border bg-background px-2"
                  />
                </td>
                <td className="text-right">{item.unit_price}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>

      <div className="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
        <label className="flex flex-col gap-1">
          Reason code
          <select
            value={reasonCode}
            data-testid="reason-code"
            onChange={(e) =>
              setReasonCode(
                e.target.value as (typeof REASON_CODES)[number],
              )
            }
            className="rounded border border-border bg-background px-2 py-1"
          >
            {REASON_CODES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            data-testid="restock-inventory"
            checked={restockInventory}
            onChange={(e) => setRestockInventory(e.target.checked)}
          />
          Restock inventory
        </label>
        <label className="col-span-2 flex flex-col gap-1">
          Notes
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="rounded border border-border bg-background p-2"
            rows={2}
          />
        </label>
      </div>

      <div className="flex items-center justify-between rounded border border-border p-3">
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground">
            Refund total
          </div>
          <div data-testid="refund-total" className="text-xl font-semibold">
            ${total.toFixed(2)}
          </div>
        </div>
        {overThreshold && (
          <div
            data-testid="approval-notice"
            role="status"
            className="rounded border border-amber-500 bg-amber-50 p-2 text-sm text-amber-900"
          >
            This refund exceeds the ${threshold.toFixed(2)} approval threshold —
            it will route to the approvals queue for sign-off before posting.
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <Button
          type="button"
          onClick={() => void submit()}
          disabled={busy || selectedItems.length === 0}
          data-testid="submit-refund"
        >
          {busy ? "Submitting…" : "Submit refund"}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => navigate(`/sales/${sale.id}`)}
        >
          Cancel
        </Button>
      </div>
    </section>
  );
}
