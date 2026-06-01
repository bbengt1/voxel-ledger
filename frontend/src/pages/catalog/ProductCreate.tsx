import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type ProductResponse = components["schemas"]["ProductResponse"];

type ComponentKind = "part" | "supply";

interface BomRow {
  key: string;
  kind: ComponentKind;
  search: string;
  options: { id: string; name: string }[];
  componentId: string;
  quantity: string;
}

let _bomKey = 0;
const nextBomKey = () => `b${++_bomKey}`;
const emptyBomRow = (): BomRow => ({
  key: nextBomKey(),
  kind: "part",
  search: "",
  options: [],
  componentId: "",
  quantity: "",
});

async function searchComponentOptions(
  kind: ComponentKind,
  search: string,
): Promise<{ id: string; name: string }[]> {
  const endpoint = kind === "part" ? "/api/v1/parts" : "/api/v1/supplies";
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  params.set("limit", "20");
  const res = await apiClient.get<{ items: { id: string; name: string }[] }>(
    `${endpoint}?${params.toString()}`,
  );
  return res.data.items;
}

export function ProductCreatePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnTo = searchParams.get("return_to");
  const [sku, setSku] = useState("");
  const [upc, setUpc] = useState("");
  const [name, setName] = useState(searchParams.get("name") ?? "");
  const [description, setDescription] = useState("");
  const [unitPrice, setUnitPrice] = useState("");
  const [weight, setWeight] = useState("");
  const [category, setCategory] = useState("");
  const [assemblyMinutes, setAssemblyMinutes] = useState("0");

  const [bomRows, setBomRows] = useState<BomRow[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [generatingUpc, setGeneratingUpc] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateBomRow(key: string, patch: Partial<BomRow>) {
    setBomRows((prev) =>
      prev.map((r) => (r.key === key ? { ...r, ...patch } : r)),
    );
  }

  async function refreshBomOptions(key: string, kind: ComponentKind, search: string) {
    try {
      const options = await searchComponentOptions(kind, search);
      updateBomRow(key, { options });
    } catch {
      /* non-fatal — leave prior options */
    }
  }

  async function onGenerateUpc() {
    setGeneratingUpc(true);
    try {
      const res = await apiClient.post<{ upc: string }>(
        "/api/v1/products/upc/generate",
        {},
      );
      setUpc(res.data.upc);
    } catch {
      setError("Could not generate UPC.");
    } finally {
      setGeneratingUpc(false);
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        name,
        unit_price: unitPrice,
      };
      if (sku.trim()) body["sku"] = sku.trim();
      if (upc.trim()) body["upc"] = upc.trim();
      if (description.trim()) body["description"] = description.trim();
      if (weight.trim()) body["weight_grams"] = weight.trim();
      const am = Number.parseInt(assemblyMinutes, 10);
      if (Number.isFinite(am) && am > 0) body["assembly_minutes"] = am;
      if (category.trim()) body["category"] = category.trim();
      // Only include complete BOM rows (component picked + positive qty).
      const bomItems = bomRows
        .filter((r) => r.componentId && Number(r.quantity) > 0)
        .map((r) => ({
          component_kind: r.kind,
          component_id: r.componentId,
          quantity: r.quantity,
        }));
      if (bomItems.length > 0) body["bom_items"] = bomItems;
      const res = await apiClient.post<ProductResponse>(
        "/api/v1/products",
        body,
      );
      if (returnTo === "job_composer") {
        const params = new URLSearchParams();
        params.set("restored", "1");
        params.set("product_id", res.data.id);
        params.set("product_label", res.data.name);
        navigate(`/production/jobs/new?${params.toString()}`);
        return;
      }
      navigate(`/catalog/products/${res.data.id}`);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not create product.";
      setError(typeof detail === "string" ? detail : "Could not create product.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="max-w-md">
      <h1 className="text-xl font-semibold">New product</h1>
      <form className="mt-6 space-y-3" onSubmit={onSubmit}>
        <label className="block text-sm">
          SKU
          <Input
            className="mt-1"
            value={sku}
            onChange={(e) => setSku(e.target.value)}
            placeholder="auto-generated"
            data-testid="sku-input"
          />
          <span className="mt-1 block text-xs text-muted-foreground">
            Leave blank to auto-generate as PROD-YYYY-NNNN.
          </span>
        </label>
        <label className="block text-sm">
          UPC
          <div className="mt-1 flex gap-2">
            <Input
              value={upc}
              onChange={(e) => setUpc(e.target.value)}
              data-testid="upc-input"
            />
            <Button
              type="button"
              variant="outline"
              onClick={onGenerateUpc}
              disabled={generatingUpc || submitting}
              data-testid="upc-generate"
            >
              {generatingUpc ? "…" : "Generate"}
            </Button>
          </div>
        </label>
        <label className="block text-sm">
          Name
          <Input
            className="mt-1"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </label>
        <label className="block text-sm">
          Description
          <Input
            className="mt-1"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          Unit price
          <Input
            className="mt-1"
            inputMode="decimal"
            value={unitPrice}
            onChange={(e) => setUnitPrice(e.target.value)}
            required
          />
        </label>
        <label className="block text-sm">
          Weight (g)
          <Input
            className="mt-1"
            inputMode="decimal"
            value={weight}
            onChange={(e) => setWeight(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          Assembly minutes
          <Input
            className="mt-1"
            type="number"
            min={0}
            value={assemblyMinutes}
            onChange={(e) => setAssemblyMinutes(e.target.value)}
            data-testid="assembly-minutes-input"
          />
          <span className="mt-1 block text-xs text-muted-foreground">
            Labor to assemble one product from its parts. Added to the
            rolled-up cost at the labor rate.
          </span>
        </label>
        <label className="block text-sm">
          Category
          <Input
            className="mt-1"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          />
        </label>

        <fieldset className="rounded border border-border p-3" data-testid="bom-fieldset">
          <legend className="px-1 text-xs uppercase text-muted-foreground">
            Bill of materials (optional)
          </legend>
          <p className="text-xs text-muted-foreground">
            Add materials, supplies, or sub-products that make up this
            product. The rolled-up cost is computed from these on save.
          </p>
          <div className="mt-3 space-y-3">
            {bomRows.map((row, idx) => (
              <div
                key={row.key}
                className="grid grid-cols-1 gap-2 rounded border border-border/60 p-2 sm:grid-cols-[7rem_1fr_5rem_auto]"
                data-testid={`bom-row-${idx}`}
              >
                <select
                  className="rounded border border-input bg-background px-2 py-1 text-sm"
                  value={row.kind}
                  onChange={(e) => {
                    const kind = e.target.value as ComponentKind;
                    updateBomRow(row.key, { kind, componentId: "", options: [] });
                    void refreshBomOptions(row.key, kind, row.search);
                  }}
                  data-testid={`bom-kind-${idx}`}
                >
                  <option value="part">Part</option>
                  <option value="supply">Supply</option>
                </select>
                <div className="space-y-1">
                  <Input
                    placeholder="Search…"
                    value={row.search}
                    onChange={(e) => {
                      const search = e.target.value;
                      updateBomRow(row.key, { search });
                      void refreshBomOptions(row.key, row.kind, search);
                    }}
                    data-testid={`bom-search-${idx}`}
                  />
                  <select
                    className="block w-full rounded border border-input bg-background px-2 py-1 text-sm"
                    value={row.componentId}
                    onChange={(e) =>
                      updateBomRow(row.key, { componentId: e.target.value })
                    }
                    onFocus={() => {
                      if (row.options.length === 0)
                        void refreshBomOptions(row.key, row.kind, row.search);
                    }}
                    data-testid={`bom-component-${idx}`}
                  >
                    <option value="">— select —</option>
                    {row.options.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.name}
                      </option>
                    ))}
                  </select>
                </div>
                <Input
                  inputMode="decimal"
                  placeholder="Qty"
                  value={row.quantity}
                  onChange={(e) =>
                    updateBomRow(row.key, { quantity: e.target.value })
                  }
                  data-testid={`bom-qty-${idx}`}
                />
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() =>
                    setBomRows((prev) => prev.filter((r) => r.key !== row.key))
                  }
                  data-testid={`bom-remove-${idx}`}
                >
                  ×
                </Button>
              </div>
            ))}
          </div>
          <Button
            type="button"
            variant="outline"
            className="mt-3"
            onClick={() => setBomRows((prev) => [...prev, emptyBomRow()])}
            data-testid="bom-add-row"
          >
            Add component
          </Button>
        </fieldset>

        {error ? (
          <p
            role="alert"
            data-testid="create-error"
            className="text-sm text-destructive"
          >
            {error}
          </p>
        ) : null}

        <div className="flex gap-2">
          <Button type="submit" disabled={submitting}>
            {submitting ? "Creating…" : "Create product"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() =>
              navigate(
                returnTo === "job_composer"
                  ? "/production/jobs/new?restored=1"
                  : "/catalog/products",
              )
            }
            disabled={submitting}
          >
            Cancel
          </Button>
        </div>
      </form>
    </section>
  );
}
