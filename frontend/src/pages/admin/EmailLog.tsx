/**
 * `/admin/email-log` — operator-facing delivery log with filters for
 * state / kind / subject substring. Per-row actions: retry, cancel, view
 * body in a new tab via `/api/v1/email-messages/{id}/body`.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { FilterBar } from "@/components/ui/FilterBar";
import { Input } from "@/components/ui/Input";

type EmailMessageResponse = components["schemas"]["EmailMessageResponse"];

const STATES = [
  "queued",
  "sending",
  "sent",
  "failed",
  "bounced",
  "cancelled",
] as const;
const KINDS = [
  "quote",
  "invoice",
  "statement",
  "recurring_invoice",
  "password_reset",
  "generic",
] as const;

export function EmailLogPage() {
  const [params, setParams] = useSearchParams();
  const stateFilter = params.get("state") ?? "";
  const kindFilter = params.get("kind") ?? "";
  const subjectFilter = params.get("subject") ?? "";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<EmailMessageResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const query = useMemo(() => {
    const q: Record<string, string> = {};
    if (stateFilter) q["state"] = stateFilter;
    if (kindFilter) q["kind"] = kindFilter;
    return q;
  }, [stateFilter, kindFilter]);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/api/v1/email-messages", { params: query });
      setItems(res.data.items);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to load.");
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  const filtered = useMemo(() => {
    const s = subjectFilter.trim().toLowerCase();
    if (!s) return items;
    return items.filter((m) => m.subject.toLowerCase().includes(s));
  }, [items, subjectFilter]);

  async function retry(id: string) {
    setBusyId(id);
    try {
      await apiClient.post(`/api/v1/email-messages/${id}/retry`, null);
      await refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not retry.");
    } finally {
      setBusyId(null);
    }
  }

  async function cancel(id: string) {
    if (!window.confirm("Cancel this message?")) return;
    setBusyId(id);
    try {
      await apiClient.post(`/api/v1/email-messages/${id}/cancel`, null);
      await refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not cancel.");
    } finally {
      setBusyId(null);
    }
  }

  function viewBody(id: string) {
    window.open(
      `/api/v1/email-messages/${id}/body`,
      "_blank",
      "noopener,noreferrer",
    );
  }

  const columns: DataTableColumn<EmailMessageResponse>[] = [
    {
      key: "subject",
      header: "Subject",
      isPrimary: true,
      cell: (m) => <span data-testid={`email-row-${m.id}`}>{m.subject}</span>,
    },
    {
      key: "to",
      header: "To",
      cell: (m) => <span className="font-mono text-xs">{m.to_address}</span>,
    },
    { key: "kind", header: "Kind", cell: (m) => m.kind },
    { key: "state", header: "State", cell: (m) => m.state },
    {
      key: "attempts",
      header: "Attempts",
      align: "right",
      cell: (m) => <span className="font-mono">{m.attempts}</span>,
    },
    {
      key: "created",
      header: "Created",
      cell: (m) => (
        <span className="text-xs">
          {new Date(m.created_at).toLocaleString()}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      align: "right",
      cardFullWidth: true,
      cell: (m) => {
        const canRetry = m.state === "failed" || m.state === "bounced";
        const canCancel = m.state === "queued" || m.state === "failed";
        return (
          <div className="flex gap-1">
            <Button
              size="sm"
              variant="outline"
              onClick={() => viewBody(m.id)}
              data-testid={`email-view-${m.id}`}
            >
              View
            </Button>
            {canRetry ? (
              <Button
                size="sm"
                disabled={busyId === m.id}
                onClick={() => void retry(m.id)}
                data-testid={`email-retry-${m.id}`}
              >
                Retry
              </Button>
            ) : null}
            {canCancel ? (
              <Button
                size="sm"
                variant="destructive"
                disabled={busyId === m.id}
                onClick={() => void cancel(m.id)}
                data-testid={`email-cancel-${m.id}`}
              >
                Cancel
              </Button>
            ) : null}
          </div>
        );
      },
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader title="Email delivery log" />

      <FilterBar columns={3}>
        <label className="block text-xs">
          State
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={stateFilter}
            onChange={(e) => updateParam("state", e.target.value)}
            data-testid="filter-state"
          >
            <option value="">All</option>
            {STATES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs">
          Kind
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={kindFilter}
            onChange={(e) => updateParam("kind", e.target.value)}
            data-testid="filter-kind"
          >
            <option value="">All</option>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs">
          Subject
          <Input
            value={subjectFilter}
            onChange={(e) => updateParam("subject", e.target.value)}
            data-testid="filter-subject"
            placeholder="substring"
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
        rows={filtered}
        getRowKey={(m) => m.id}
        loading={loading && filtered.length === 0}
        emptyMessage="No messages."
        minWidthClassName="min-w-[760px]"
      />
    </section>
  );
}
