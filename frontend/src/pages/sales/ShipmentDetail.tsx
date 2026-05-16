/**
 * `/sales/shipments/:id` — shipment detail with state-gated actions:
 * purchase-label (pending), mark-shipped, mark-delivered. "Print label"
 * opens the PDF endpoint in a new tab.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";

type ShipmentResponse = components["schemas"]["ShipmentResponse"];

interface Transition {
  label: string;
  path: "purchase-label" | "mark-shipped" | "mark-delivered" | "cancel";
  variant?: "default" | "secondary" | "outline" | "destructive";
  allowedStates: ReadonlyArray<string>;
}

const TRANSITIONS: readonly Transition[] = [
  {
    label: "Purchase label",
    path: "purchase-label",
    variant: "default",
    allowedStates: ["pending"],
  },
  {
    label: "Mark shipped",
    path: "mark-shipped",
    variant: "secondary",
    allowedStates: ["label_purchased", "pending"],
  },
  {
    label: "Mark delivered",
    path: "mark-delivered",
    variant: "secondary",
    allowedStates: ["shipped"],
  },
  {
    label: "Cancel",
    path: "cancel",
    variant: "destructive",
    allowedStates: ["pending", "label_purchased"],
  },
];

export function ShipmentDetailPage() {
  const { id } = useParams<{ id: string }>();

  const [shipment, setShipment] = useState<ShipmentResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refetch = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(
        `/api/v1/shipments/${id}` as "/api/v1/shipments/{shipment_id}",
      );
      setShipment(res.data as unknown as ShipmentResponse);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : "Failed to load shipment.",
      );
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  async function transition(path: Transition["path"]) {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      await apiClient.post(`/api/v1/shipments/${id}/${path}`, {});
      await refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : `Could not ${path}.`);
    } finally {
      setBusy(false);
    }
  }

  if (loading && !shipment) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (error && !shipment) {
    return (
      <div role="alert" className="text-sm text-destructive">
        {error}
      </div>
    );
  }
  if (!shipment) return null;

  const allowed = TRANSITIONS.filter((t) =>
    t.allowedStates.includes(shipment.state),
  );

  const labelHref =
    shipment.state !== "pending"
      ? `/api/v1/shipments/${shipment.id}/label.pdf`
      : null;

  const shipTo = shipment.ship_to as Record<string, unknown>;

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Shipment</h1>
          <p className="text-sm text-muted-foreground">
            State: <span data-testid="shipment-state">{shipment.state}</span> ·{" "}
            Carrier: {shipment.carrier}
            {shipment.tracking_number ? (
              <>
                {" · Tracking: "}
                {shipment.tracking_url ? (
                  <a
                    className="hover:underline"
                    href={shipment.tracking_url}
                    target="_blank"
                    rel="noreferrer"
                    data-testid="tracking-link"
                  >
                    {shipment.tracking_number}
                  </a>
                ) : (
                  shipment.tracking_number
                )}
              </>
            ) : null}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link to={`/sales/${shipment.sale_id}`}>Back to sale</Link>
          </Button>
          {labelHref ? (
            <Button asChild variant="secondary">
              <a
                href={labelHref}
                target="_blank"
                rel="noreferrer"
                data-testid="print-label-link"
              >
                Print label
              </a>
            </Button>
          ) : null}
        </div>
      </header>

      {error ? (
        <div role="alert" className="text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {allowed.length > 0 ? (
        <div className="flex flex-wrap gap-2" data-testid="shipment-actions">
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
        </div>
      ) : null}

      <div className="rounded-lg border border-border p-4 text-sm">
        <h2 className="font-semibold">Ship to</h2>
        <dl className="mt-2 grid grid-cols-2 gap-y-1">
          <dt className="text-muted-foreground">Name</dt>
          <dd>{String(shipTo["name"] ?? "")}</dd>
          <dt className="text-muted-foreground">Street</dt>
          <dd>
            {String(shipTo["street1"] ?? "")}
            {shipTo["street2"] ? `, ${String(shipTo["street2"])}` : ""}
          </dd>
          <dt className="text-muted-foreground">City</dt>
          <dd>
            {String(shipTo["city"] ?? "")}, {String(shipTo["state"] ?? "")}{" "}
            {String(shipTo["postal_code"] ?? "")}
          </dd>
          <dt className="text-muted-foreground">Country</dt>
          <dd>{String(shipTo["country"] ?? "")}</dd>
        </dl>
      </div>

      <div className="rounded-lg border border-border p-4 text-sm">
        <h2 className="font-semibold">Parcel</h2>
        <dl className="mt-2 grid grid-cols-2 gap-y-1">
          <dt className="text-muted-foreground">Weight (g)</dt>
          <dd className="font-mono">{shipment.weight_grams ?? "—"}</dd>
          <dt className="text-muted-foreground">Service level</dt>
          <dd>{shipment.service_level ?? "—"}</dd>
          <dt className="text-muted-foreground">Cost</dt>
          <dd className="font-mono">${shipment.cost_amount}</dd>
        </dl>
      </div>
    </section>
  );
}
