/**
 * `/banking/transactions` — list with state/date/search filters. Per-row
 * inline actions: match, post-and-match, ignore, unmatch.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { BankAccountPicker } from "@/components/banking/BankAccountPicker";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { FilterBar } from "@/components/ui/FilterBar";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";
import { ManualMatchModal } from "./ManualMatchModal";
import { PostJournalEntryModal } from "./PostJournalEntryModal";

type Tx = components["schemas"]["BankTransactionResponse"];

const STATES = ["unmatched", "matched", "ignored", "cleared"] as const;
const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

export function TransactionsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const accountId = params.get("account_id") ?? "";
  const stateFilter = params.get("state") ?? "unmatched";
  const dateFrom = params.get("date_from") ?? "";
  const dateTo = params.get("date_to") ?? "";
  const search = params.get("search") ?? "";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<Tx[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [matchTxId, setMatchTxId] = useState<string | null>(null);
  const [postJeTx, setPostJeTx] = useState<Tx | null>(null);

  const query = useMemo(() => {
    const q: Record<string, string> = {};
    if (accountId) q["account_id"] = accountId;
    if (stateFilter && stateFilter !== "all") q["state"] = stateFilter;
    if (dateFrom) q["date_from"] = dateFrom;
    if (dateTo) q["date_to"] = dateTo;
    if (search) q["search"] = search;
    return q;
  }, [accountId, stateFilter, dateFrom, dateTo, search]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/api/v1/bank-transactions", { params: query });
      setItems(res.data.items);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : "Failed to load transactions.",
      );
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  async function ignore(id: string) {
    try {
      await apiClient.post(`/api/v1/bank-transactions/${id}/ignore`);
      await load();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not ignore.");
    }
  }

  async function unmatch(id: string) {
    try {
      await apiClient.post(`/api/v1/bank-transactions/${id}/unmatch`);
      await load();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not unmatch.");
    }
  }

  const columns: DataTableColumn<Tx>[] = [
    {
      key: "date",
      header: "Date",
      isPrimary: true,
      cell: (t) => <span data-testid={`tx-row-${t.id}`}>{t.occurred_on}</span>,
    },
    { key: "description", header: "Description", cell: (t) => t.description },
    {
      key: "amount",
      header: "Amount",
      align: "right",
      cell: (t) => {
        const n = Number.parseFloat(t.amount);
        const positive = Number.isFinite(n) && n >= 0;
        return (
          <span
            className={
              "font-mono " +
              (positive ? "text-emerald-600" : "text-destructive")
            }
          >
            {t.amount}
          </span>
        );
      },
    },
    {
      key: "state",
      header: "State",
      cell: (t) => (
        <span className="rounded bg-muted px-2 py-0.5 text-xs">{t.state}</span>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      align: "right",
      cardFullWidth: true,
      cell: (t) =>
        canWrite ? (
          <div className="flex justify-end gap-1">
            {t.state === "unmatched" ? (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setMatchTxId(t.id)}
                  data-testid={`tx-match-${t.id}`}
                >
                  Match
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setPostJeTx(t)}
                  data-testid={`tx-post-${t.id}`}
                >
                  Post + match
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => void ignore(t.id)}
                  data-testid={`tx-ignore-${t.id}`}
                >
                  Ignore
                </Button>
              </>
            ) : t.state === "matched" ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => void unmatch(t.id)}
                data-testid={`tx-unmatch-${t.id}`}
              >
                Unmatch
              </Button>
            ) : null}
          </div>
        ) : null,
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader title="Bank transactions" />

      <FilterBar columns={5}>
        <label className="block text-xs">
          Account
          <BankAccountPicker
            value={accountId}
            onChange={(id) => updateParam("account_id", id)}
            data-testid="tx-filter-account"
          />
        </label>
        <label className="block text-xs">
          State
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={stateFilter}
            onChange={(e) => updateParam("state", e.target.value)}
            data-testid="tx-filter-state"
          >
            <option value="all">All</option>
            {STATES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs">
          From
          <Input
            type="date"
            value={dateFrom}
            onChange={(e) => updateParam("date_from", e.target.value)}
            data-testid="tx-filter-from"
          />
        </label>
        <label className="block text-xs">
          To
          <Input
            type="date"
            value={dateTo}
            onChange={(e) => updateParam("date_to", e.target.value)}
            data-testid="tx-filter-to"
          />
        </label>
        <label className="block text-xs">
          Search
          <Input
            value={search}
            onChange={(e) => updateParam("search", e.target.value)}
            data-testid="tx-filter-search"
          />
        </label>
      </FilterBar>

      {error ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(t) => t.id}
        loading={loading && items.length === 0}
        emptyMessage="No transactions."
        minWidthClassName="min-w-[640px]"
      />

      <ManualMatchModal
        txId={matchTxId ?? ""}
        open={matchTxId !== null}
        onOpenChange={(next) => {
          if (!next) setMatchTxId(null);
        }}
        onDone={() => void load()}
      />
      <PostJournalEntryModal
        tx={postJeTx}
        open={postJeTx !== null}
        onOpenChange={(next) => {
          if (!next) setPostJeTx(null);
        }}
        onDone={() => void load()}
      />
    </section>
  );
}
