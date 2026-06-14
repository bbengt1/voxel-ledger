/**
 * `/sales/:id` — sale detail. Header, lines, COGS breakdown panel,
 * state-gated action bar, and a footer that lists linked shipments.
 *
 * Refunds list is deferred to 6.7b (the refund flow lives in that PR).
 * The "Create refund" action button is still surfaced here when the sale
 * state permits it; clicking simply navigates to /sales/:id/refund/new
 * which 6.7b owns.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type SaleResponse = components["schemas"]["SaleResponse"];
type SaleCogsBreakdownResponse =
  components["schemas"]["SaleCogsBreakdownResponse"];
type ShipmentResponse = components["schemas"]["ShipmentResponse"];

const WRITE_ROLES: readonly string[] = ["owner", "sales", "bookkeeper"];

interface Transition {
  label: string;
  path: string;
  variant?: "default" | "secondary" | "destructive";
  allowedStates: ReadonlyArray<SaleResponse["state"]>;
}

const TRANSITIONS: readonly Transition[] = [
  {
    label: "Confirm",
    path: "confirm",
    variant: "default",
    allowedStates: ["draft"],
  },
  {
    label: "Fulfill",
    path: "fulfill",
    variant: "secondary",
    allowedStates: ["confirmed"],
  },
  {
    label: "Cancel",
    path: "cancel",
    variant: "destructive",
    allowedStates: ["draft", "confirmed"],
  },
];

interface PostingInfo {
  journal_entry_id?: string | null;
  inventory_transaction_ids?: string[] | null;
}

export function SaleDetailPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? WRITE_ROLES.includes(role) : false;

  const [sale, setSale] = useState<SaleResponse | null>(null);
  const [cogs, setCogs] = useState<SaleCogsBreakdownResponse | null>(null);
  const [shipments, setShipments] = useState<ShipmentResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refetch = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(
        `/api/v1/sales/${id}` as "/api/v1/sales/{sale_id}",
      );
      setSale(res.data as unknown as SaleResponse);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to load sale.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  // COGS preview (confirmed/fulfilled sales only — service returns 422
  // for drafts; we just skip the call).
  useEffect(() => {
    if (!sale || sale.state === "draft" || sale.state === "cancelled") return;
    let cancelled = false;
    api
      .get(
        `/api/v1/sales/${sale.id}/cogs-preview` as "/api/v1/sales/{sale_id}/cogs-preview",
      )
      .then((res) => {
        if (!cancelled) {
          setCogs(res.data as unknown as SaleCogsBreakdownResponse);
        }
      })
      .catch(() => {
        /* non-fatal */
      });
    return () => {
      cancelled = true;
    };
  }, [sale]);

  // Shipments for this sale.
  useEffect(() => {
    if (!sale) return;
    let cancelled = false;
    apiClient
      .get<{ items: ShipmentResponse[] } | ShipmentResponse[]>(
        `/api/v1/sales/${sale.id}/shipments`,
      )
      .then((res) => {
        if (cancelled) return;
        const data = res.data as unknown;
        if (Array.isArray(data)) {
          setShipments(data as ShipmentResponse[]);
        } else if (data && typeof data === "object" && "items" in data) {
          setShipments(
            ((data as { items: ShipmentResponse[] }).items ??
              []) as ShipmentResponse[],
          );
        }
      })
      .catch(() => {
        /* non-fatal */
      });
    return () => {
      cancelled = true;
    };
  }, [sale]);

  async function transition(path: string) {
    if (!id) return;
    setBusy(true);
    try {
      await apiClient.post(`/api/v1/sales/${id}/${path}`);
      await refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : `Could not ${path} sale.`,
      );
    } finally {
      setBusy(false);
    }
  }

  if (loading && !sale) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (error && !sale) {
    return (
      <div role="alert" className="text-sm text-destructive">
        {error}
      </div>
    );
  }
  if (!sale) return null;

  const allowed = TRANSITIONS.filter((t) => t.allowedStates.includes(sale.state));
  const postingInfo = (sale as unknown as PostingInfo) ?? {};

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">
            Sale {sale.sale_number}
          </h1>
          <p className="text-sm text-muted-foreground">
            State: <span data-testid="sale-state">{sale.state}</span> ·{" "}
            {sale.customer_name} ·{" "}
            {new Date(sale.occurred_at).toLocaleString()}
          </p>
        </div>
        <div className="flex gap-2">
          {sale.state === "draft" ? (
            <Button asChild variant="outline">
              <Link to={`/sales/${sale.id}`}>Edit</Link>
            </Button>
          ) : null}
          <Button variant="outline" asChild>
            <Link to="/sales">Back to sales</Link>
          </Button>
        </div>
      </header>

      {error ? (
        <div role="alert" className="text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {canWrite && allowed.length > 0 ? (
        <div className="flex flex-wrap gap-2" data-testid="sale-actions">
          {allowed.map((t) => (
            <Button
              key={t.path}
              variant={t.variant ?? "default"}
              disabled={busy}
              onClick={() => void transition(t.path)}
              data-testid={`transition-${t.path}`}
            >
              {t.label}
            </Button>
          ))}
          {sale.state === "confirmed" || sale.state === "fulfilled" ? (
            <>
              <Button
                variant="outline"
                onClick={() => navigate(`/sales/${sale.id}/refund/new`)}
                data-testid="create-refund-btn"
              >
                Create refund
              </Button>
              <Button
                variant="outline"
                onClick={() => navigate(`/sales/${sale.id}/shipments/new`)}
                data-testid="create-shipment-btn"
              >
                Create shipment
              </Button>
            </>
          ) : null}
        </div>
      ) : null}

      <div className="rounded-lg border border-border p-4">
        <h2 className="text-sm font-semibold">Lines</h2>
        <div className="overflow-x-auto">
        <table className="mt-2 w-full min-w-[480px] table-fixed border-collapse text-sm">
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
            {(sale.items ?? []).map((it) => (
              <tr
                key={it.id}
                className="border-b border-border/50"
                data-testid={`sale-line-${it.id}`}
              >
                <td className="py-2 pr-2 font-mono text-xs">{it.line_number}</td>
                <td className="py-2 pr-2">{it.kind}</td>
                <td className="py-2 pr-2">{it.description}</td>
                <td className="py-2 pr-2 text-right font-mono">{it.quantity}</td>
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
            <dd className="text-right font-mono">${sale.subtotal}</dd>
            <dt className="text-muted-foreground">Discount</dt>
            <dd className="text-right font-mono">−${sale.discount_amount}</dd>
            <dt className="text-muted-foreground">Shipping</dt>
            <dd className="text-right font-mono">${sale.shipping_amount}</dd>
            <dt className="text-muted-foreground">Tax</dt>
            <dd className="text-right font-mono">${sale.tax_amount}</dd>
            <dt className="text-muted-foreground">Channel fee</dt>
            <dd className="text-right font-mono">
              ${sale.channel_fee_amount}
            </dd>
            <dt className="font-semibold">Total</dt>
            <dd className="text-right font-mono font-semibold">
              ${sale.total_amount}
            </dd>
          </dl>
        </div>

        <div className="rounded-lg border border-border p-4 text-sm">
          <h2 className="font-semibold">COGS</h2>
          {cogs ? (
            <div className="mt-2 space-y-1" data-testid="cogs-panel">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Total cost</span>
                <span className="font-mono">${cogs.total_cost}</span>
              </div>
              <ul className="text-xs">
                {(cogs.lines ?? []).map((ln) => (
                  <li
                    key={ln.line_number}
                    className="flex justify-between border-t border-border/50 py-1"
                  >
                    <span>
                      #{ln.line_number} {ln.description} ({ln.kind})
                    </span>
                    <span className="font-mono">${ln.cost}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="mt-2 text-xs text-muted-foreground">
              {sale.state === "draft"
                ? "COGS is only available after confirm."
                : "Loading COGS…"}
            </p>
          )}
        </div>
      </div>

      {postingInfo.journal_entry_id ? (
        <div
          className="rounded-lg border border-border p-4 text-sm"
          data-testid="posting-panel"
        >
          <h2 className="font-semibold">Posted entry</h2>
          <p className="mt-1 text-xs">
            Journal entry:{" "}
            <span
              className="font-mono"
              data-testid="posted-journal-entry-id"
            >
              {postingInfo.journal_entry_id}
            </span>
          </p>
          {postingInfo.inventory_transaction_ids?.length ? (
            <p className="mt-1 text-xs text-muted-foreground">
              {postingInfo.inventory_transaction_ids.length} inventory tx
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="rounded-lg border border-border p-4 text-sm">
        <h2 className="font-semibold">Shipments</h2>
        {shipments.length === 0 ? (
          <p className="mt-1 text-xs text-muted-foreground">
            No shipments yet.
          </p>
        ) : (
          <ul className="mt-2 space-y-1 text-xs">
            {shipments.map((s) => (
              <li
                key={s.id}
                data-testid={`shipment-link-${s.id}`}
                className="flex justify-between border-b border-border/50 py-1"
              >
                <Link
                  to={`/sales/shipments/${s.id}`}
                  className="font-mono hover:underline"
                >
                  {s.id.slice(0, 8)}
                </Link>
                <span>{s.state}</span>
                <span>{s.carrier}</span>
                <span className="font-mono">${s.cost_amount}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
