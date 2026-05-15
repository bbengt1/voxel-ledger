/**
 * Journal entries list — filter card backed by URL state, cursor pagination,
 * click-through to detail page.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import {
  AccountPicker,
  type AccountOption,
} from "@/components/accounting/AccountPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type JournalEntryResponse = components["schemas"]["JournalEntryResponse"];
type JournalEntryListResponse =
  components["schemas"]["JournalEntryListResponse"];
type AccountingPeriodResponse =
  components["schemas"]["AccountingPeriodResponse"];

interface ActorLite {
  id: string;
  email: string;
}

export function JournalEntriesListPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const accountId = searchParams.get("account_id") ?? "";
  const periodId = searchParams.get("period_id") ?? "";
  const fromAt = searchParams.get("from_at") ?? "";
  const toAt = searchParams.get("to_at") ?? "";
  const cursor = searchParams.get("cursor") ?? "";

  const [items, setItems] = useState<JournalEntryResponse[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [prevCursors, setPrevCursors] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [periods, setPeriods] = useState<AccountingPeriodResponse[]>([]);
  const [accountOption, setAccountOption] = useState<AccountOption | null>(null);
  const [actors, setActors] = useState<Map<string, string>>(new Map());
  const [periodNames, setPeriodNames] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    let cancelled = false;
    api
      .get("/api/v1/accounting/periods")
      .then((res) => {
        if (cancelled) return;
        setPeriods(res.data.items);
        setPeriodNames(new Map(res.data.items.map((p) => [p.id, p.name])));
      })
      .catch(() => {
        if (!cancelled) setPeriods([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const params = useMemo(() => {
    const p: Record<string, string> = {};
    if (accountId) p["account_id"] = accountId;
    if (periodId) p["period_id"] = periodId;
    if (fromAt) p["from_at"] = fromAt;
    if (toAt) p["to_at"] = toAt;
    if (cursor) p["cursor"] = cursor;
    return p;
  }, [accountId, periodId, fromAt, toAt, cursor]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/accounting/entries", { params })
      .then((res) => {
        if (cancelled) return;
        const data = res.data as JournalEntryListResponse;
        setItems(data.items);
        setNextCursor(data.next_cursor ?? null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load entries.";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [params]);

  // Best-effort actor email lookups.
  useEffect(() => {
    const missing = Array.from(
      new Set(
        items
          .map((e) => e.actor_user_id)
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
          .catch(() => [id, id.slice(0, 8)] as const),
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

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Journal entries</h1>
        <Button asChild>
          <Link to="/accounting/entries/new">New entry</Link>
        </Button>
      </header>

      <div className="rounded-md border border-border bg-muted/20 p-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="flex flex-col gap-1 text-xs font-medium">
            Account
            <AccountPicker
              value={accountOption}
              onChange={(opt) => {
                setAccountOption(opt);
                updateFilter("account_id", opt?.id ?? "");
              }}
              data-testid="filter-account"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium">
            Period
            <select
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              value={periodId}
              onChange={(e) => updateFilter("period_id", e.target.value)}
              data-testid="filter-period"
            >
              <option value="">All</option>
              {periods.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.state})
                </option>
              ))}
            </select>
          </label>
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
        </div>
      </div>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Entry #</th>
            <th className="py-2 pr-2">Posted</th>
            <th className="py-2 pr-2">Description</th>
            <th className="py-2 pr-2 text-right">Total debits</th>
            <th className="py-2 pr-2">Actor</th>
            <th className="py-2 pr-2">Period</th>
            <th className="py-2 pr-2">Status</th>
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
                No entries match the current filters.
              </td>
            </tr>
          ) : (
            items.map((e) => {
              const totalDebits = e.lines
                .reduce((s, ln) => s + Number(ln.debit || 0), 0)
                .toFixed(2);
              const desc = e.description ?? "";
              const descTrim = desc.length > 50 ? desc.slice(0, 47) + "…" : desc;
              return (
                <tr key={e.id} className="border-b border-border/50">
                  <td className="py-2 pr-2 font-mono text-xs">
                    <Link
                      to={`/accounting/entries/${e.id}`}
                      className="hover:underline"
                    >
                      {e.entry_number}
                    </Link>
                  </td>
                  <td className="py-2 pr-2 text-xs">
                    {new Date(e.posted_at).toLocaleDateString()}
                  </td>
                  <td className="py-2 pr-2" title={desc}>
                    {descTrim}
                  </td>
                  <td className="py-2 pr-2 text-right tabular-nums">
                    {totalDebits}
                  </td>
                  <td className="py-2 pr-2 text-xs">
                    {actors.get(e.actor_user_id) ?? "…"}
                  </td>
                  <td className="py-2 pr-2 text-xs">
                    {periodNames.get(e.period_id) ?? "—"}
                  </td>
                  <td className="py-2 pr-2 text-xs">
                    {e.is_reversed ? (
                      <span className="rounded bg-muted px-1.5 py-0.5">
                        reversed
                      </span>
                    ) : e.reversal_of_entry_id ? (
                      <span className="rounded bg-muted px-1.5 py-0.5">
                        reversal
                      </span>
                    ) : (
                      "—"
                    )}
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
    </section>
  );
}
