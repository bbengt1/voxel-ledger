import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { BomTab } from "@/pages/catalog/BomTab";
import { useAuthStore } from "@/store/useAuthStore";

type ProductResponse = components["schemas"]["ProductResponse"];

const CAN_WRITE_ROLES = ["owner", "production", "sales"] as const;

export function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const role = useAuthStore((s) => s.user?.role);
  const isOwner = role === "owner";
  const canWrite = role
    ? (CAN_WRITE_ROLES as readonly string[]).includes(role)
    : false;

  const [product, setProduct] = useState<ProductResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [unitPrice, setUnitPrice] = useState("");
  const [weight, setWeight] = useState("");
  const [category, setCategory] = useState("");
  const [upc, setUpc] = useState("");

  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  function syncFormFromProduct(p: ProductResponse) {
    setName(p.name);
    setDescription(p.description ?? "");
    setUnitPrice(p.unit_price);
    setWeight(p.weight_grams ?? "");
    setCategory(p.category ?? "");
    setUpc(p.upc ?? "");
  }

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    apiClient
      .get<ProductResponse>(`/api/v1/products/${id}`)
      .then((res) => {
        if (cancelled) return;
        setProduct(res.data);
        syncFormFromProduct(res.data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load product.";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function save() {
    if (!id) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const body: Record<string, unknown> = {
        name,
        unit_price: unitPrice,
      };
      body["description"] = description.trim() || null;
      body["upc"] = upc.trim() || null;
      body["weight_grams"] = weight.trim() || null;
      body["category"] = category.trim() || null;
      const res = await apiClient.patch<ProductResponse>(
        `/api/v1/products/${id}`,
        body,
      );
      setProduct(res.data);
      syncFormFromProduct(res.data);
      setSaveMsg("Saved.");
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Save failed.";
      setSaveMsg(typeof detail === "string" ? detail : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function doArchive() {
    if (!id) return;
    try {
      const res = await apiClient.post<ProductResponse>(
        `/api/v1/products/${id}/archive`,
      );
      setProduct(res.data);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not archive.";
      setSaveMsg(detail);
    }
  }

  async function doUnarchive() {
    if (!id) return;
    try {
      const res = await apiClient.post<ProductResponse>(
        `/api/v1/products/${id}/unarchive`,
      );
      setProduct(res.data);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not unarchive.";
      setSaveMsg(detail);
    }
  }

  if (loading) return <p>Loading…</p>;
  if (error || !product)
    return (
      <div role="alert" className="text-destructive">
        {error ?? "Product not found."}
      </div>
    );

  return (
    <section className="max-w-2xl space-y-6">
      <header>
        <h1 className="text-xl font-semibold">{product.name}</h1>
        <p className="text-sm text-muted-foreground">
          <span className="font-mono text-xs">{product.sku}</span> ·{" "}
          {product.is_archived ? "Archived" : "Active"} ·{" "}
          <span data-testid="unit-price">Price {product.unit_price}</span> ·{" "}
          <span data-testid="unit-cost">
            Cost{" "}
            {product.unit_cost_cached ??
              "— (no BOM cost data)"}
          </span>
        </p>
      </header>

      {canWrite ? (
        <fieldset className="space-y-3" data-testid="edit-form">
          <legend className="text-sm font-medium">Profile</legend>
          <label className="block text-sm">
            Name
            <Input
              className="mt-1"
              value={name}
              onChange={(e) => setName(e.target.value)}
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
              data-testid="unit-price-input"
            />
          </label>
          <label className="block text-sm">
            UPC
            <Input
              className="mt-1"
              value={upc}
              onChange={(e) => setUpc(e.target.value)}
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
            Category
            <Input
              className="mt-1"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />
          </label>
          <div className="flex gap-2">
            <Button onClick={save} disabled={saving} data-testid="save-btn">
              {saving ? "Saving…" : "Save"}
            </Button>
            <Button
              variant="outline"
              onClick={() => navigate("/catalog/products")}
            >
              Back
            </Button>
          </div>
          {saveMsg ? (
            <p role="status" data-testid="save-msg" className="text-sm">
              {saveMsg}
            </p>
          ) : null}
        </fieldset>
      ) : null}

      <section
        className="space-y-2 border-t border-border pt-4"
        data-testid="bom-section"
      >
        <BomTab productId={product.id} />
      </section>

      {isOwner ? (
        <section className="space-y-2 border-t border-border pt-4">
          <h2 className="text-sm font-semibold">Lifecycle</h2>
          <div className="flex gap-2">
            {product.is_archived ? (
              <Button onClick={doUnarchive} data-testid="unarchive-btn">
                Unarchive
              </Button>
            ) : (
              <Button
                variant="destructive"
                onClick={doArchive}
                data-testid="archive-btn"
              >
                Archive
              </Button>
            )}
          </div>
        </section>
      ) : null}
    </section>
  );
}
