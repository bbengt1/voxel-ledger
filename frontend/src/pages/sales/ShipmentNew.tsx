/**
 * `/sales/:id/shipments/new` — ship-to address form, weight, dimensions,
 * carrier hint. Submits to POST /api/v1/sales/{sale_id}/shipments and
 * redirects to /sales/shipments/:id.
 *
 * Best-effort default ship-to: if a previous shipment exists on this
 * sale, pre-fill from it. The "look up last-used per customer-email"
 * is left as a nice-to-have until a search endpoint exists.
 */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type ShipmentResponse = components["schemas"]["ShipmentResponse"];
type ShipmentCreate = components["schemas"]["ShipmentCreate"];

const CARRIERS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "", label: "Use default" },
  { value: "shippo", label: "Shippo" },
  { value: "easypost", label: "EasyPost" },
  { value: "static", label: "Static (manual)" },
];

export function ShipmentNewPage() {
  const navigate = useNavigate();
  const { id: saleId } = useParams<{ id: string }>();

  const [name, setName] = useState("");
  const [street1, setStreet1] = useState("");
  const [street2, setStreet2] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [postal, setPostal] = useState("");
  const [country, setCountry] = useState("US");
  const [weightGrams, setWeightGrams] = useState("");
  const [lengthCm, setLengthCm] = useState("");
  const [widthCm, setWidthCm] = useState("");
  const [heightCm, setHeightCm] = useState("");
  const [carrier, setCarrier] = useState("");
  const [serviceLevel, setServiceLevel] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Try to default ship-to from a prior shipment on this sale.
  useEffect(() => {
    if (!saleId) return;
    let cancelled = false;
    apiClient
      .get<{ items: ShipmentResponse[] } | ShipmentResponse[]>(
        `/api/v1/sales/${saleId}/shipments`,
      )
      .then((res) => {
        if (cancelled) return;
        const data = res.data as unknown;
        const items: ShipmentResponse[] = Array.isArray(data)
          ? (data as ShipmentResponse[])
          : ((data as { items?: ShipmentResponse[] }).items ?? []);
        const last = items[items.length - 1];
        if (!last) return;
        const to = last.ship_to as Record<string, unknown>;
        if (typeof to["name"] === "string") setName(to["name"] as string);
        if (typeof to["street1"] === "string") setStreet1(to["street1"] as string);
        if (typeof to["street2"] === "string") setStreet2(to["street2"] as string);
        if (typeof to["city"] === "string") setCity(to["city"] as string);
        if (typeof to["state"] === "string") setState(to["state"] as string);
        if (typeof to["postal_code"] === "string")
          setPostal(to["postal_code"] as string);
        if (typeof to["country"] === "string")
          setCountry(to["country"] as string);
      })
      .catch(() => {
        /* non-fatal */
      });
    return () => {
      cancelled = true;
    };
  }, [saleId]);

  async function onSubmit() {
    if (!saleId) return;
    setSubmitting(true);
    setError(null);
    try {
      const body: ShipmentCreate = {
        ship_to: {
          name,
          street1,
          street2: street2 || undefined,
          city,
          state,
          postal_code: postal,
          country,
        },
      };
      if (weightGrams) body.weight_grams = Number.parseInt(weightGrams, 10);
      if (lengthCm || widthCm || heightCm) {
        body.dimensions_cm = {
          length: Number.parseFloat(lengthCm) || 0,
          width: Number.parseFloat(widthCm) || 0,
          height: Number.parseFloat(heightCm) || 0,
        };
      }
      if (carrier) body.carrier_hint = carrier;
      if (serviceLevel.trim()) body.service_level = serviceLevel.trim();

      const res = await apiClient.post<ShipmentResponse>(
        `/api/v1/sales/${saleId}/shipments`,
        body,
      );
      navigate(`/sales/shipments/${res.data.id}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : "Could not create shipment.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="max-w-xl space-y-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">New shipment</h1>
        <Button
          variant="outline"
          onClick={() => navigate(`/sales/${saleId}`)}
          disabled={submitting}
        >
          Cancel
        </Button>
      </header>

      <div className="space-y-3 rounded-lg border border-border p-4">
        <h2 className="text-sm font-semibold">Ship to</h2>
        <label className="block text-sm">
          Recipient name
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            data-testid="ship-name"
          />
        </label>
        <label className="block text-sm">
          Street
          <Input
            value={street1}
            onChange={(e) => setStreet1(e.target.value)}
            data-testid="ship-street1"
          />
        </label>
        <label className="block text-sm">
          Street (line 2)
          <Input
            value={street2}
            onChange={(e) => setStreet2(e.target.value)}
            data-testid="ship-street2"
          />
        </label>
        <div className="grid grid-cols-3 gap-2">
          <label className="block text-sm">
            City
            <Input
              value={city}
              onChange={(e) => setCity(e.target.value)}
              data-testid="ship-city"
            />
          </label>
          <label className="block text-sm">
            State / region
            <Input
              value={state}
              onChange={(e) => setState(e.target.value)}
              data-testid="ship-state"
            />
          </label>
          <label className="block text-sm">
            Postal
            <Input
              value={postal}
              onChange={(e) => setPostal(e.target.value)}
              data-testid="ship-postal"
            />
          </label>
        </div>
        <label className="block text-sm">
          Country (ISO-2)
          <Input
            value={country}
            onChange={(e) => setCountry(e.target.value.toUpperCase())}
            maxLength={2}
            data-testid="ship-country"
          />
        </label>
      </div>

      <div className="space-y-3 rounded-lg border border-border p-4">
        <h2 className="text-sm font-semibold">Parcel</h2>
        <label className="block text-sm">
          Weight (g)
          <Input
            type="number"
            min={0}
            value={weightGrams}
            onChange={(e) => setWeightGrams(e.target.value)}
            data-testid="ship-weight"
          />
        </label>
        <div className="grid grid-cols-3 gap-2">
          <label className="block text-sm">
            Length (cm)
            <Input
              type="number"
              min={0}
              step="0.1"
              value={lengthCm}
              onChange={(e) => setLengthCm(e.target.value)}
              data-testid="ship-length"
            />
          </label>
          <label className="block text-sm">
            Width (cm)
            <Input
              type="number"
              min={0}
              step="0.1"
              value={widthCm}
              onChange={(e) => setWidthCm(e.target.value)}
              data-testid="ship-width"
            />
          </label>
          <label className="block text-sm">
            Height (cm)
            <Input
              type="number"
              min={0}
              step="0.1"
              value={heightCm}
              onChange={(e) => setHeightCm(e.target.value)}
              data-testid="ship-height"
            />
          </label>
        </div>
        <label className="block text-sm">
          Carrier
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={carrier}
            onChange={(e) => setCarrier(e.target.value)}
            data-testid="ship-carrier"
          >
            {CARRIERS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          Service level (optional)
          <Input
            value={serviceLevel}
            onChange={(e) => setServiceLevel(e.target.value)}
            placeholder="usps_priority, ups_ground, ..."
            data-testid="ship-service-level"
          />
        </label>
      </div>

      {error ? (
        <p
          role="alert"
          data-testid="shipment-error"
          className="text-sm text-destructive"
        >
          {error}
        </p>
      ) : null}

      <div className="flex gap-2">
        <Button
          disabled={submitting}
          onClick={() => void onSubmit()}
          data-testid="shipment-create-btn"
        >
          {submitting ? "Creating…" : "Create shipment"}
        </Button>
      </div>
    </section>
  );
}
