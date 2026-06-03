import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { ProductImage } from "@/components/catalog/ProductImage";
import { OnHandSection } from "@/components/inventory/OnHandSection";
import { AttachmentsSection } from "@/components/platform/AttachmentsSection";
import { NotesSection } from "@/components/platform/NotesSection";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { formatCurrency, useCurrency } from "@/lib/currency";
import { BomTab } from "@/pages/catalog/BomTab";
import { useAuthStore } from "@/store/useAuthStore";

type ProductResponse = components["schemas"]["ProductResponse"];
type BuildableResponse = components["schemas"]["BuildableResponse"];
type BuildResponse = components["schemas"]["BuildResponse"];

const CAN_WRITE_ROLES = ["owner", "production", "sales"] as const;
// Assembling a product from its parts mutates inventory — owner/production
// only (matches the builds API role gate).
const CAN_BUILD_ROLES = ["owner", "production"] as const;

export function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const role = useAuthStore((s) => s.user?.role);
  const isOwner = role === "owner";
  const canWrite = role
    ? (CAN_WRITE_ROLES as readonly string[]).includes(role)
    : false;
  const canBuild = role
    ? (CAN_BUILD_ROLES as readonly string[]).includes(role)
    : false;
  const currency = useCurrency();

  const [product, setProduct] = useState<ProductResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [unitPrice, setUnitPrice] = useState("");
  const [weight, setWeight] = useState("");
  const [category, setCategory] = useState("");
  const [upc, setUpc] = useState("");
  const [assemblyMinutes, setAssemblyMinutes] = useState("0");

  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [generatingUpc, setGeneratingUpc] = useState(false);
  const [imageKey, setImageKey] = useState(0);
  const [imageBusy, setImageBusy] = useState(false);

  // "Build from parts" — one-click assembly that consumes parts/supplies
  // and credits product inventory. `buildable` is the max assemblable now.
  const [buildable, setBuildable] = useState<number | null>(null);
  const [buildQty, setBuildQty] = useState("1");
  const [building, setBuilding] = useState(false);
  const [buildMsg, setBuildMsg] = useState<string | null>(null);

  // Derived material rollup (grams from the product's parts), with names
  // resolved from the materials catalog. Refetched when the BOM changes.
  const [materialRollup, setMaterialRollup] = useState<Record<string, string>>({});
  const [materialNames, setMaterialNames] = useState<Record<string, string>>({});
  const [materialsKey, setMaterialsKey] = useState(0);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    Promise.all([
      apiClient.get<{ materials: Record<string, string> }>(
        `/api/v1/products/${id}/materials`,
      ),
      apiClient.get<{ items: { id: string; name: string }[] }>("/api/v1/materials", {
        params: { is_archived: "false" },
      }),
    ])
      .then(([rollupRes, matRes]) => {
        if (cancelled) return;
        setMaterialRollup(rollupRes.data.materials ?? {});
        const names: Record<string, string> = {};
        for (const m of matRes.data.items) names[m.id] = m.name;
        setMaterialNames(names);
      })
      .catch(() => {
        /* non-fatal */
      });
    return () => {
      cancelled = true;
    };
  }, [id, materialsKey]);

  async function onUploadImage(file: File) {
    if (!id) return;
    setImageBusy(true);
    setSaveMsg(null);
    try {
      const form = new FormData();
      form.append("file", file);
      await apiClient.post(`/api/v1/products/${id}/image`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setImageKey((k) => k + 1);
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not upload image.";
      setSaveMsg(typeof detail === "string" ? detail : "Could not upload image.");
    } finally {
      setImageBusy(false);
    }
  }

  async function onRemoveImage() {
    if (!id) return;
    setImageBusy(true);
    try {
      await apiClient.delete(`/api/v1/products/${id}/image`);
      setImageKey((k) => k + 1);
    } catch {
      setSaveMsg("Could not remove image.");
    } finally {
      setImageBusy(false);
    }
  }

  /** Pull an image off the clipboard and upload it. Tries the async
   * Clipboard API (button click); the section's onPaste handler covers
   * the Ctrl/Cmd+V path, which also works over plain HTTP where
   * `clipboard.read()` may be blocked. */
  async function onPasteButton() {
    setSaveMsg(null);
    try {
      const items = await navigator.clipboard.read();
      for (const item of items) {
        const type = item.types.find((t) => t.startsWith("image/"));
        if (type) {
          const blob = await item.getType(type);
          const ext = type.split("/")[1] ?? "png";
          await onUploadImage(
            new File([blob], `pasted.${ext}`, { type }),
          );
          return;
        }
      }
      setSaveMsg("No image found on the clipboard.");
    } catch {
      setSaveMsg(
        "Couldn't read the clipboard — copy an image, then click into this box and press Ctrl/Cmd+V.",
      );
    }
  }

  function onPasteImage(e: React.ClipboardEvent) {
    const file = Array.from(e.clipboardData.items)
      .find((it) => it.type.startsWith("image/"))
      ?.getAsFile();
    if (file) {
      e.preventDefault();
      void onUploadImage(file);
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
      setSaveMsg("Could not generate UPC.");
    } finally {
      setGeneratingUpc(false);
    }
  }

  function syncFormFromProduct(p: ProductResponse) {
    setName(p.name);
    setDescription(p.description ?? "");
    setUnitPrice(p.unit_price);
    setWeight(p.weight_grams ?? "");
    setCategory(p.category ?? "");
    setUpc(p.upc ?? "");
    setAssemblyMinutes(String(p.assembly_minutes ?? 0));
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

  function refreshBuildable() {
    if (!id || !canBuild) return;
    apiClient
      .get<BuildableResponse>("/api/v1/builds/buildable", {
        params: { product_id: id },
      })
      .then((res) => setBuildable(res.data.max_buildable))
      .catch(() => setBuildable(null));
  }

  function refreshProduct() {
    if (!id) return;
    apiClient
      .get<ProductResponse>(`/api/v1/products/${id}`)
      .then((res) => setProduct(res.data))
      .catch(() => {});
  }

  useEffect(() => {
    refreshBuildable();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, canBuild]);

  async function doBuild() {
    if (!id) return;
    const qty = Number.parseInt(buildQty, 10);
    if (!Number.isFinite(qty) || qty <= 0) {
      setBuildMsg("Quantity must be at least 1.");
      return;
    }
    setBuilding(true);
    setBuildMsg(null);
    try {
      const res = await apiClient.post<BuildResponse>("/api/v1/builds/now", {
        product_id: id,
        quantity: qty,
      });
      setBuildMsg(
        `Built ${qty} — parts consumed and product inventory updated (build ${res.data.build_number}).`,
      );
      refreshProduct();
      refreshBuildable();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })
        .response?.data?.detail;
      let msg = "Could not build.";
      if (typeof detail === "string") msg = detail;
      else if (detail && typeof detail === "object" && "message" in detail) {
        msg = String((detail as { message: unknown }).message);
      }
      setBuildMsg(msg);
    } finally {
      setBuilding(false);
    }
  }

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
      const am = Number.parseInt(assemblyMinutes, 10);
      body["assembly_minutes"] = Number.isFinite(am) && am > 0 ? am : 0;
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
          <span data-testid="unit-price">
            Price {formatCurrency(product.unit_price, currency)}
          </span>{" "}
          ·{" "}
          <span data-testid="unit-cost">
            Cost{" "}
            {product.unit_cost_cached
              ? formatCurrency(product.unit_cost_cached, currency)
              : "— (no BOM cost data)"}
          </span>
        </p>
      </header>

      <OnHandSection
        entityKind="product"
        entityId={product.id}
        entityName={product.name}
        totalOnHand={product.total_on_hand}
        perLocationOnHand={product.per_location_on_hand ?? null}
        unit="ea"
        lowStockThreshold={product.low_stock_threshold ?? null}
        onChanged={refreshProduct}
      />

      {canBuild ? (
        <section
          className="space-y-3 rounded-lg border border-border p-4"
          data-testid="build-section"
        >
          <h2 className="text-sm font-semibold">Build from parts</h2>
          <p className="text-sm text-muted-foreground">
            Assemble this product from its parts &amp; supplies. Building
            consumes part inventory and adds finished product to stock.
          </p>
          <p className="text-sm" data-testid="buildable-count">
            {buildable === null
              ? "Checking availability…"
              : buildable > 0
                ? `Can build ${buildable} from current parts inventory.`
                : "Not enough parts in stock to build this product."}
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <label className="block text-sm">
              Quantity
              <Input
                className="mt-1 w-24"
                type="number"
                min={1}
                max={buildable ?? undefined}
                value={buildQty}
                onChange={(e) => setBuildQty(e.target.value)}
                data-testid="build-qty-input"
              />
            </label>
            <Button
              type="button"
              onClick={() => void doBuild()}
              disabled={
                building ||
                buildable === null ||
                buildable <= 0 ||
                Number.parseInt(buildQty, 10) > buildable
              }
              data-testid="build-now-btn"
            >
              {building ? "Building…" : "Build now"}
            </Button>
          </div>
          {buildMsg ? (
            <p role="status" data-testid="build-msg" className="text-sm">
              {buildMsg}
            </p>
          ) : null}
        </section>
      ) : null}

      <section
        className="space-y-2 rounded-lg border border-border p-4"
        data-testid="product-image-section"
      >
        <h2 className="text-sm font-semibold">Image</h2>
        <div className="flex items-start gap-4">
          <ProductImage
            productId={product.id}
            size="full"
            refreshKey={imageKey}
            className="h-40 w-40 border border-border"
            alt={`${product.name} image`}
          />
          {canWrite ? (
            <div className="space-y-2 text-sm">
              {/* Paste target: click to focus, then Ctrl/Cmd+V. This path
                  works even over plain HTTP where the async Clipboard API
                  is blocked. */}
              <div
                role="button"
                tabIndex={0}
                onPaste={onPasteImage}
                className="cursor-text rounded border border-dashed border-input bg-muted/30 px-3 py-2 text-xs text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                data-testid="product-image-paste-zone"
              >
                Click here and press Ctrl/Cmd+V to paste an image
              </div>
              <label className="block">
                <span className="text-xs text-muted-foreground">
                  …or choose a file (uploading replaces the current image)
                </span>
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  disabled={imageBusy}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void onUploadImage(f);
                    e.target.value = "";
                  }}
                  data-testid="product-image-input"
                  className="mt-1 block text-sm"
                />
              </label>
              <p className="text-xs text-muted-foreground">
                PNG, JPEG, or WEBP. Shown on the product page and in POS.
              </p>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={imageBusy}
                  onClick={() => void onPasteButton()}
                  data-testid="product-image-paste-btn"
                >
                  Paste from clipboard
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={imageBusy}
                  onClick={() => void onRemoveImage()}
                  data-testid="product-image-remove"
                >
                  Remove image
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      </section>

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
                disabled={generatingUpc || saving}
                data-testid="upc-generate"
              >
                {generatingUpc ? "…" : "Generate"}
              </Button>
            </div>
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
        <BomTab
          productId={product.id}
          onChanged={() => {
            if (!id) return;
            // The BOM rollup recomputes server-side; re-fetch so the
            // header's rolled-up Cost (and material rollup) reflect the
            // change without a reload. A changed BOM also changes what can
            // be built, so refresh that too.
            refreshProduct();
            refreshBuildable();
            setMaterialsKey((k) => k + 1);
          }}
        />
      </section>

      <section
        className="space-y-2 border-t border-border pt-4"
        data-testid="material-rollup-section"
      >
        <h2 className="text-sm font-semibold">Materials (from parts)</h2>
        {Object.keys(materialRollup).length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No material usage — add parts to this product's BOM.
          </p>
        ) : (
          <div className="overflow-x-auto">
          <table className="w-full min-w-[320px] text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                <th className="py-1 pr-2">Material</th>
                <th className="py-1 pr-2 text-right">Grams / product</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(materialRollup).map(([mid, grams]) => (
                <tr key={mid} className="border-b border-border/50">
                  <td className="py-1 pr-2">{materialNames[mid] ?? mid}</td>
                  <td className="py-1 pr-2 text-right tabular-nums">
                    {Number(grams).toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
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

      {/* Phase 2.6: notes + attachments */}
      {id ? (
        <>
          <NotesSection entityKind="product" entityId={id} />
          <AttachmentsSection entityKind="product" entityId={id} />
        </>
      ) : null}
    </section>
  );
}
