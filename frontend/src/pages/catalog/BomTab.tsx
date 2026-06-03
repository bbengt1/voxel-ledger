import { useCallback, useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { formatCurrency, useCurrency } from "@/lib/currency";
import { useAuthStore } from "@/store/useAuthStore";

type ComponentKind = "part" | "supply";

type BomItem = {
  id: string;
  parent_product_id: string;
  component_kind: ComponentKind;
  component_id: string;
  quantity: string;
  notes: string | null;
  resolved_name: string;
  resolved_unit_cost: string | null;
  line_cost: string | null;
};

type BomListResponse = {
  items: BomItem[];
  total_cost: string | null;
};

type LookupOption = { id: string; name: string };

const CAN_EDIT_ROLES = ["owner", "production"] as const;

function extractDetail(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: string } } }).response
    ?.data?.detail;
  return typeof detail === "string" && detail.length > 0 ? detail : fallback;
}

async function searchOptions(
  kind: ComponentKind,
  search: string,
): Promise<LookupOption[]> {
  const endpoint = kind === "part" ? "/api/v1/parts" : "/api/v1/supplies";
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  params.set("limit", "20");
  const res = await apiClient.get<{
    items: { id: string; name: string }[];
  }>(`${endpoint}?${params.toString()}`);
  return res.data.items;
}

export function BomTab({
  productId,
  onChanged,
}: {
  productId: string;
  /** Fired after a BOM mutation lands so the parent can refresh the
   * product's rolled-up cost (``unit_cost_cached``). */
  onChanged?: () => void;
}) {
  const role = useAuthStore((s) => s.user?.role);
  const currency = useCurrency();
  const fmtCost = (s: string | null): string =>
    s === null ? "—" : formatCurrency(s, currency);
  const canEdit = role
    ? (CAN_EDIT_ROLES as readonly string[]).includes(role)
    : false;

  const [items, setItems] = useState<BomItem[]>([]);
  const [totalCost, setTotalCost] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [showAdd, setShowAdd] = useState(false);
  const [kind, setKind] = useState<ComponentKind>("part");
  const [search, setSearch] = useState("");
  const [options, setOptions] = useState<LookupOption[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [quantity, setQuantity] = useState("");
  const [notes, setNotes] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editQty, setEditQty] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      const res = await apiClient.get<BomListResponse>(
        `/api/v1/products/${productId}/bom`,
      );
      setItems(res.data.items);
      setTotalCost(res.data.total_cost);
    } catch (err: unknown) {
      setListError(extractDetail(err, "Failed to load BOM."));
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!showAdd) return;
    let cancelled = false;
    void searchOptions(kind, search).then((opts) => {
      if (!cancelled) setOptions(opts);
    });
    return () => {
      cancelled = true;
    };
  }, [showAdd, kind, search]);

  async function submitAdd() {
    setAddError(null);
    if (!selectedId || !quantity) {
      setAddError("Pick a component and enter a quantity.");
      return;
    }
    setSubmitting(true);
    try {
      await apiClient.post(`/api/v1/products/${productId}/bom`, {
        component_kind: kind,
        component_id: selectedId,
        quantity,
        notes: notes.trim() || null,
      });
      setShowAdd(false);
      setSelectedId("");
      setQuantity("");
      setNotes("");
      setSearch("");
      await refresh();
      onChanged?.();
    } catch (err: unknown) {
      setAddError(extractDetail(err, "Failed to add component."));
    } finally {
      setSubmitting(false);
    }
  }

  async function saveEdit(itemId: string) {
    try {
      await apiClient.patch(`/api/v1/products/${productId}/bom/${itemId}`, {
        quantity: editQty,
      });
      setEditingId(null);
      await refresh();
      onChanged?.();
    } catch (err: unknown) {
      setListError(extractDetail(err, "Failed to update quantity."));
    }
  }

  async function confirmDelete(itemId: string) {
    try {
      await apiClient.delete(`/api/v1/products/${productId}/bom/${itemId}`);
      setDeletingId(null);
      await refresh();
      onChanged?.();
    } catch (err: unknown) {
      setListError(extractDetail(err, "Failed to delete component."));
    }
  }

  return (
    <section className="space-y-4" data-testid="bom-tab">
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Bill of materials</h2>
        {canEdit ? (
          <Button
            onClick={() => setShowAdd(true)}
            data-testid="bom-add-btn"
            disabled={showAdd}
          >
            Add component
          </Button>
        ) : null}
      </header>

      {listError ? (
        <p role="alert" className="text-destructive text-sm">
          {listError}
        </p>
      ) : null}

      {loading ? (
        <p>Loading BOM…</p>
      ) : items.length === 0 ? (
        <p className="text-muted-foreground text-sm">No components yet.</p>
      ) : (
        <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm" data-testid="bom-table">
          <thead>
            <tr className="border-b">
              <th className="py-1 text-left">Kind</th>
              <th className="py-1 text-left">Name</th>
              <th className="py-1 text-right">Quantity</th>
              <th className="py-1 text-right">Unit cost</th>
              <th className="py-1 text-right">Line cost</th>
              {canEdit ? <th /> : null}
            </tr>
          </thead>
          <tbody>
            {items.map((it) => (
              <tr key={it.id} className="border-b" data-testid={`bom-row-${it.id}`}>
                <td className="py-1 pr-2">{it.component_kind}</td>
                <td className="py-1 pr-2">{it.resolved_name}</td>
                <td className="py-1 pr-2 text-right">
                  {editingId === it.id ? (
                    <Input
                      data-testid={`bom-edit-input-${it.id}`}
                      value={editQty}
                      onChange={(e) => setEditQty(e.target.value)}
                      inputMode="decimal"
                    />
                  ) : (
                    it.quantity
                  )}
                </td>
                <td className="py-1 pr-2 text-right">
                  {fmtCost(it.resolved_unit_cost)}
                </td>
                <td className="py-1 pr-2 text-right">
                  {fmtCost(it.line_cost)}
                </td>
                {canEdit ? (
                  <td className="py-1 text-right">
                    {editingId === it.id ? (
                      <>
                        <Button
                          onClick={() => void saveEdit(it.id)}
                          data-testid={`bom-save-edit-${it.id}`}
                        >
                          Save
                        </Button>
                        <Button
                          variant="outline"
                          onClick={() => setEditingId(null)}
                        >
                          Cancel
                        </Button>
                      </>
                    ) : deletingId === it.id ? (
                      <>
                        <Button
                          variant="destructive"
                          onClick={() => void confirmDelete(it.id)}
                          data-testid={`bom-confirm-delete-${it.id}`}
                        >
                          Confirm delete
                        </Button>
                        <Button
                          variant="outline"
                          onClick={() => setDeletingId(null)}
                        >
                          Cancel
                        </Button>
                      </>
                    ) : (
                      <>
                        <Button
                          variant="outline"
                          onClick={() => {
                            setEditingId(it.id);
                            setEditQty(it.quantity);
                          }}
                          data-testid={`bom-edit-${it.id}`}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="destructive"
                          onClick={() => setDeletingId(it.id)}
                          data-testid={`bom-delete-${it.id}`}
                        >
                          Delete
                        </Button>
                      </>
                    )}
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}

      <aside
        className="border-border rounded border p-3 text-sm"
        data-testid="bom-rollup"
      >
        <strong>Rolled-up cost: </strong>
        {totalCost === null
          ? "Cost unknown — some components missing cost data"
          : formatCurrency(totalCost, currency)}
      </aside>

      {showAdd && canEdit ? (
        <div
          className="border-border bg-card space-y-3 rounded border p-4"
          data-testid="bom-add-form"
        >
          {addError ? (
            <p
              role="alert"
              className="text-destructive text-sm"
              data-testid="bom-add-error"
            >
              {addError}
            </p>
          ) : null}
          <label className="block text-sm">
            Component kind
            <select
              className="border-input mt-1 block w-full rounded border p-1"
              value={kind}
              onChange={(e) => {
                setKind(e.target.value as ComponentKind);
                setSelectedId("");
              }}
              data-testid="bom-add-kind"
            >
              <option value="part">Part</option>
              <option value="supply">Supply</option>
            </select>
          </label>
          <label className="block text-sm">
            Search
            <Input
              className="mt-1"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              data-testid="bom-add-search"
            />
          </label>
          <label className="block text-sm">
            Component
            <select
              className="border-input mt-1 block w-full rounded border p-1"
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              data-testid="bom-add-component"
            >
              <option value="">— select —</option>
              {options.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            Quantity
            <Input
              className="mt-1"
              inputMode="decimal"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              data-testid="bom-add-qty"
            />
          </label>
          <label className="block text-sm">
            Notes
            <Input
              className="mt-1"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              data-testid="bom-add-notes"
            />
          </label>
          <div className="flex gap-2">
            <Button
              onClick={() => void submitAdd()}
              disabled={submitting}
              data-testid="bom-add-submit"
            >
              {submitting ? "Adding…" : "Add"}
            </Button>
            <Button variant="outline" onClick={() => setShowAdd(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
