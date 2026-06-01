/**
 * Inventory transactions ledger view.
 *
 * URL-state-backed filters so links are shareable. Cursor pagination
 * via the backend's ``next_cursor``. Two top-right CTAs: record + transfer
 * (role-aware, but the backend still enforces).
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { RecordTransactionModal } from "@/components/inventory/RecordTransactionModal";
import { TransferStockModal } from "@/components/inventory/TransferStockModal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type InventoryTransactionResponse =
  components["schemas"]["InventoryTransactionResponse"];
type InventoryTransactionListResponse =
  components["schemas"]["InventoryTransactionListResponse"];
type InventoryLocationResponse =
  components["schemas"]["InventoryLocationResponse"];

type Kind = InventoryTransactionResponse["kind"];

const ALL_KINDS: ReadonlyArray<{ value: Kind; label: string; icon: string }> = [
  { value: "production_in", label: "Production in", icon: "↗" },
  { value: "sale_out", label: "Sale out", icon: "↘" },
  { value: "adjustment", label: "Adjustment", icon: "±" },
  { value: "return_in", label: "Return in", icon: "↩" },
  { value: "waste", label: "Waste", icon: "✗" },
  { value: "receipt", label: "Receipt", icon: "+" },
  { value: "transfer_in", label: "Transfer in", icon: "→" },
  { value: "transfer_out", label: "Transfer out", icon: "←" },
];

const KIND_BY_VALUE = new Map(ALL_KINDS.map((k) => [k.value, k] as const));

const TRANSFER_ROLES = new Set(["owner", "production"]);
const RECORD_ROLES = new Set(["owner", "production", "sales"]);

interface ActorLite {
  id: string;
  email: string;
}

export function TransactionsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canRecord = !!role && RECORD_ROLES.has(role);
  const canTransfer = !!role && TRANSFER_ROLES.has(role);

  const [searchParams, setSearchParams] = useSearchParams();

  const entityKind = searchParams.get("entity_kind") ?? "";
  const entityId = searchParams.get("entity_id") ?? "";
  const locationId = searchParams.get("location_id") ?? "";
  const fromAt = searchParams.get("from_at") ?? "";
  const toAt = searchParams.get("to_at") ?? "";
  const cursor = searchParams.get("cursor") ?? "";
  // Multi-select kinds: store as comma-separated in URL.
  const kindsParam = searchParams.get("kinds") ?? "";
  const selectedKinds = useMemo(
    () =>
      new Set(
        kindsParam
          .split(",")
          .filter(Boolean)
          .filter((k): k is Kind => KIND_BY_VALUE.has(k as Kind)),
      ),
    [kindsParam],
  );

  const [items, setItems] = useState<InventoryTransactionResponse[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [prevCursors, setPrevCursors] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [locations, setLocations] = useState<InventoryLocationResponse[]>([]);
  const [actors, setActors] = useState<Map<string, string>>(new Map());

  const [recordOpen, setRecordOpen] = useState(false);
  const [transferOpen, setTransferOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  // Load locations once for the filter dropdown.
  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<{ items: InventoryLocationResponse[] }>(
        "/api/v1/inventory/locations",
        { params: { is_archived: "false" } },
      )
      .then((res) => {
        if (cancelled) return;
        setLocations(res.data.items);
      })
      .catch(() => {
        if (!cancelled) setLocations([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const params: Record<string, string> = {};
    if (entityKind) params["entity_kind"] = entityKind;
    if (entityId) params["entity_id"] = entityId;
    if (locationId) params["location_id"] = locationId;
    if (fromAt) params["from_at"] = fromAt;
    if (toAt) params["to_at"] = toAt;
    if (cursor) params["cursor"] = cursor;
    // The backend filter is single-kind; if exactly one kind is picked,
    // delegate; otherwise we filter client-side on the returned page.
    if (selectedKinds.size === 1) {
      params["kind"] = Array.from(selectedKinds)[0]!;
    }
    apiClient
      .get<InventoryTransactionListResponse>("/api/v1/inventory/transactions", {
        params,
      })
      .then((res) => {
        if (cancelled) return;
        let rows = res.data.items;
        if (selectedKinds.size > 1) {
          rows = rows.filter((r) => selectedKinds.has(r.kind));
        }
        setItems(rows);
        setNextCursor(res.data.next_cursor ?? null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load transactions.";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [entityKind, entityId, locationId, fromAt, toAt, cursor, selectedKinds]);

  // Best-effort actor lookup for rows that have an actor id.
  useEffect(() => {
    const missing = Array.from(
      new Set(
        items
          .map((tx) => tx.actor_user_id)
          .filter((id): id is string => !!id && !actors.has(id)),
      ),
    );
    if (missing.length === 0) return;
    let cancelled = false;
    Promise.all(
      missing.map((id) =>
        apiClient
          .get<ActorLite>(`/api/v1/users/${id}`)
          .then((res) => [id, res.data.email] as const)
          .catch(() => [id, "system"] as const),
      ),
    ).then((pairs) => {
      if (cancelled) return;
      setActors((prev) => {
        const next = new Map(prev);
        for (const [id, email] of pairs) next.set(id, email);
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [items, actors]);

  function updateFilter(name: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(name, value);
    else next.delete(name);
    next.delete("cursor");
    setPrevCursors([]);
    setSearchParams(next);
  }

  function toggleKind(k: Kind) {
    const next = new Set(selectedKinds);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    updateFilter("kinds", Array.from(next).join(","));
  }

  function goNext() {
    if (!nextCursor) return;
    setPrevCursors((p) => [...p, cursor]);
    const next = new URLSearchParams(searchParams);
    next.set("cursor", nextCursor);
    setSearchParams(next);
  }

  function goPrev() {
    if (prevCursors.length === 0) return;
    const popped = prevCursors[prevCursors.length - 1] ?? "";
    setPrevCursors((p) => p.slice(0, -1));
    const next = new URLSearchParams(searchParams);
    if (popped) next.set("cursor", popped);
    else next.delete("cursor");
    setSearchParams(next);
  }

  function refresh() {
    // Force refetch by nudging searchParams (clear cursor).
    const next = new URLSearchParams(searchParams);
    next.delete("cursor");
    setPrevCursors([]);
    setSearchParams(next);
  }

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Inventory transactions</h1>
        <div className="flex gap-2">
          {canRecord ? (
            <Button
              onClick={() => setRecordOpen(true)}
              data-testid="open-record"
            >
              Record transaction
            </Button>
          ) : null}
          {canTransfer ? (
            <Button
              variant="outline"
              onClick={() => setTransferOpen(true)}
              data-testid="open-transfer"
            >
              Transfer stock
            </Button>
          ) : null}
        </div>
      </header>

      {toast ? (
        <p
          role="status"
          data-testid="tx-toast"
          className="rounded border border-border bg-muted/40 px-3 py-2 text-sm"
        >
          {toast}
        </p>
      ) : null}

      <div className="rounded-md border border-border bg-muted/20 p-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="flex flex-col gap-1 text-xs font-medium">
            From
            <Input
              type="date"
              value={fromAt}
              onChange={(e) => updateFilter("from_at", e.target.value)}
              data-testid="filter-from"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium">
            To
            <Input
              type="date"
              value={toAt}
              onChange={(e) => updateFilter("to_at", e.target.value)}
              data-testid="filter-to"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium">
            Entity kind
            <select
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              value={entityKind}
              onChange={(e) => updateFilter("entity_kind", e.target.value)}
              data-testid="filter-entity-kind"
            >
              <option value="">All</option>
              <option value="material">Material</option>
              <option value="supply">Supply</option>
              <option value="product">Product</option>
              <option value="part">Part</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium">
            Location
            <select
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              value={locationId}
              onChange={(e) => updateFilter("location_id", e.target.value)}
              data-testid="filter-location"
            >
              <option value="">All</option>
              {locations.map((loc) => (
                <option key={loc.id} value={loc.id}>
                  {loc.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="mt-3">
          <span className="text-xs font-medium">Kinds</span>
          <div
            className="mt-1 flex flex-wrap gap-1"
            data-testid="filter-kinds"
          >
            {ALL_KINDS.map((k) => {
              const active = selectedKinds.has(k.value);
              return (
                <button
                  key={k.value}
                  type="button"
                  onClick={() => toggleKind(k.value)}
                  data-testid={`kind-chip-${k.value}`}
                  aria-pressed={active}
                  className={
                    "rounded-full border px-2 py-0.5 text-xs " +
                    (active
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-background text-foreground hover:bg-accent")
                  }
                >
                  {k.icon} {k.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {error ? (
        <div
          role="alert"
          data-testid="tx-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Occurred</th>
            <th className="py-2 pr-2">Kind</th>
            <th className="py-2 pr-2">Entity</th>
            <th className="py-2 pr-2">Location</th>
            <th className="py-2 pr-2 text-right">Qty</th>
            <th className="py-2 pr-2">Actor</th>
            <th className="py-2 pr-2">Reason</th>
          </tr>
        </thead>
        <tbody>
          {loading && items.length === 0 ? (
            <tr>
              <td colSpan={7} className="py-4 text-center text-muted-foreground">
                Loading…
              </td>
            </tr>
          ) : items.length === 0 ? (
            <tr>
              <td colSpan={7} className="py-4 text-center text-muted-foreground">
                No transactions match the current filters.
              </td>
            </tr>
          ) : (
            items.map((tx) => {
              const kindInfo = KIND_BY_VALUE.get(tx.kind);
              const qty = Number(tx.quantity);
              const negative =
                tx.kind === "sale_out" ||
                tx.kind === "waste" ||
                tx.kind === "transfer_out" ||
                (tx.kind === "adjustment" && qty < 0);
              const entityHref =
                tx.entity_kind === "material"
                  ? `/catalog/materials/${tx.entity_id}`
                  : tx.entity_kind === "supply"
                    ? `/catalog/supplies/${tx.entity_id}`
                    : `/catalog/products/${tx.entity_id}`;
              const reason = tx.reason ?? "";
              const reasonTrim =
                reason.length > 50 ? reason.slice(0, 47) + "…" : reason;
              return (
                <tr key={tx.id} className="border-b border-border/50">
                  <td className="py-2 pr-2 text-xs">
                    {new Date(tx.occurred_at).toLocaleString()}
                  </td>
                  <td className="py-2 pr-2">
                    <span aria-hidden="true">{kindInfo?.icon ?? ""}</span>{" "}
                    <span>{kindInfo?.label ?? tx.kind}</span>
                  </td>
                  <td className="py-2 pr-2">
                    <Link to={entityHref} className="hover:underline">
                      {tx.entity_kind}:{tx.entity_id.slice(0, 8)}…
                    </Link>
                  </td>
                  <td className="py-2 pr-2">
                    <Link
                      to={`/inventory/locations/${tx.location_id}`}
                      className="hover:underline"
                    >
                      {locations.find((l) => l.id === tx.location_id)?.name ??
                        tx.location_id.slice(0, 8) + "…"}
                    </Link>
                  </td>
                  <td
                    className={
                      "py-2 pr-2 text-right tabular-nums " +
                      (negative
                        ? "text-destructive"
                        : "text-emerald-600 dark:text-emerald-400")
                    }
                  >
                    {negative && !tx.quantity.startsWith("-") ? "-" : ""}
                    {tx.quantity}
                  </td>
                  <td className="py-2 pr-2 text-xs">
                    {tx.actor_user_id
                      ? (actors.get(tx.actor_user_id) ?? "…")
                      : "system"}
                  </td>
                  <td
                    className="py-2 pr-2 text-xs"
                    title={reason || undefined}
                  >
                    {reasonTrim}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>

      <div className="flex justify-between">
        <Button
          variant="outline"
          onClick={goPrev}
          disabled={prevCursors.length === 0}
          data-testid="prev-page"
        >
          Previous
        </Button>
        <Button
          variant="outline"
          onClick={goNext}
          disabled={!nextCursor}
          data-testid="next-page"
        >
          Next
        </Button>
      </div>

      <RecordTransactionModal
        open={recordOpen}
        onClose={() => setRecordOpen(false)}
        onRecorded={(_tx, summary) => {
          setToast(summary);
          refresh();
        }}
        role={role}
      />

      <TransferStockModal
        open={transferOpen}
        onClose={() => setTransferOpen(false)}
        onTransferred={() => {
          setToast("Transfer recorded.");
          refresh();
        }}
      />
    </section>
  );
}
