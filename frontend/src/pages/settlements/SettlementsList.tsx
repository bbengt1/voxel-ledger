/**
 * `/settlements` — settlement list with channel + state filters
 * (Phase 9.10b, #162).
 */
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { FilterBar } from "@/components/ui/FilterBar";
import { useAuthStore } from "@/store/useAuthStore";

type SettlementResponse = components["schemas"]["SettlementResponse"];
type SalesChannelResponse = components["schemas"]["SalesChannelResponse"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

export function SettlementsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const state = params.get("state") ?? "";
  const channelId = params.get("channel_id") ?? "";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<SettlementResponse[]>([]);
  const [channels, setChannels] = useState<SalesChannelResponse[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get("/api/v1/sales-channels")
      .then((res) => setChannels(res.data.items))
      .catch(() => {
        /* non-fatal */
      });
  }, []);

  useEffect(() => {
    const q: Record<string, string> = {};
    if (state) q["state"] = state;
    if (channelId) q["channel_id"] = channelId;
    api
      .get("/api/v1/settlements", { params: q })
      .then((res) => setItems(res.data.items))
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } }).response
          ?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load settlements.");
      });
  }, [state, channelId]);

  const columns: DataTableColumn<SettlementResponse>[] = [
    {
      key: "settlement_number",
      header: "#",
      isPrimary: true,
      cell: (s) => (
        <Link
          to={`/settlements/${s.id}`}
          className="font-mono text-xs hover:underline"
        >
          {s.settlement_number}
        </Link>
      ),
    },
    {
      key: "period",
      header: "Period",
      cell: (s) => (
        <span className="text-xs">
          {s.period_start} → {s.period_end}
        </span>
      ),
    },
    {
      key: "gross_amount",
      header: "Gross",
      align: "right",
      cell: (s) => s.gross_amount,
    },
    {
      key: "fee_amount",
      header: "Fees",
      align: "right",
      cell: (s) => s.fee_amount,
    },
    {
      key: "payout_amount",
      header: "Payout",
      align: "right",
      cell: (s) => s.payout_amount,
    },
    {
      key: "state",
      header: "State",
      cell: (s) => (
        <span className="rounded bg-muted px-1.5 py-0.5 text-xs">{s.state}</span>
      ),
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Settlements"
        actions={
          canWrite ? (
            <Button asChild>
              <Link to="/settlements/import">Import settlement</Link>
            </Button>
          ) : null
        }
      />

      <FilterBar columns={2}>
        <label className="block text-xs">
          Channel
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={channelId}
            onChange={(e) => updateParam("channel_id", e.target.value)}
            data-testid="filter-channel"
          >
            <option value="">All</option>
            {channels.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs">
          State
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={state}
            onChange={(e) => updateParam("state", e.target.value)}
            data-testid="filter-state"
          >
            <option value="">All</option>
            <option value="imported">Imported</option>
            <option value="matched">Matched</option>
            <option value="posted">Posted</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </label>
      </FilterBar>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(s) => s.id}
        emptyMessage="No settlements yet."
        minWidthClassName="min-w-[640px]"
        rowClassName={() => "hover:bg-accent/30"}
      />
    </section>
  );
}
