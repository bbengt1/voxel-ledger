/**
 * Approval-queue list view (Phase 4.4).
 *
 * Owner and bookkeeper roles see every request the backend returns;
 * other roles see only their own requests — the API scopes the query
 * for us, so the page simply renders ``GET /api/v1/approvals``.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { PageHeader } from "@/components/layout/PageHeader";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";

interface ApprovalRow {
  id: string;
  request_type: string;
  subject_kind: string;
  subject_id: string;
  requested_by_user_id: string;
  requested_at: string;
  state: "pending" | "approved" | "rejected" | "cancelled";
  threshold_amount: string | null;
}

interface ApprovalsListResponse {
  items: ApprovalRow[];
  next_cursor: string | null;
}

export function ApprovalsListPage() {
  const [searchParams] = useSearchParams();
  const banner = searchParams.get("banner");
  const [items, setItems] = useState<ApprovalRow[]>([]);
  const [stateFilter, setStateFilter] = useState<string>("pending");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const params: Record<string, string> = {};
    if (stateFilter) params.state = stateFilter;
    apiClient
      .get<ApprovalsListResponse>("/api/v1/approvals", { params })
      .then((res) => {
        if (cancelled) return;
        setItems(res.data.items ?? []);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load approvals.";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [stateFilter]);

  const rows = useMemo(() => items, [items]);

  const columns: DataTableColumn<ApprovalRow>[] = [
    {
      key: "request_type",
      header: "Type",
      isPrimary: true,
      cell: (row) => row.request_type,
    },
    {
      key: "subject",
      header: "Subject",
      cell: (row) => (
        <>
          {row.subject_kind}:{row.subject_id.slice(0, 8)}
        </>
      ),
    },
    { key: "state", header: "State", cell: (row) => row.state },
    {
      key: "threshold",
      header: "Threshold",
      align: "right",
      cell: (row) => row.threshold_amount ?? "—",
    },
    {
      key: "requested",
      header: "Requested",
      cell: (row) => new Date(row.requested_at).toLocaleString(),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      cardFullWidth: true,
      cell: (row) => (
        <span className="space-x-2">
          <Link to={`/approvals/${row.id}`} className="text-primary underline">
            Open
          </Link>
          {row.subject_kind === "refund" && (
            <Link
              to={`/sales/refunds/${row.subject_id}`}
              data-testid={`view-refund-${row.id}`}
              className="text-primary underline"
            >
              View refund
            </Link>
          )}
        </span>
      ),
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title={
          <h1 className="text-2xl font-semibold tracking-tight">Approvals</h1>
        }
        actions={
          <label className="text-sm text-muted-foreground">
            State{" "}
            <select
              data-testid="state-filter"
              value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)}
              className="ml-2 rounded border border-border bg-background px-2 py-1"
            >
              <option value="">all</option>
              <option value="pending">pending</option>
              <option value="approved">approved</option>
              <option value="rejected">rejected</option>
              <option value="cancelled">cancelled</option>
            </select>
          </label>
        }
      />

      {banner === "refund-pending" && (
        <div
          role="status"
          data-testid="banner-refund-pending"
          className="rounded border border-amber-500 bg-amber-50 p-3 text-sm text-amber-900"
        >
          Refund submitted — routed for approval. Awaiting sign-off below.
        </div>
      )}

      {error && (
        <div role="alert" className="rounded border border-destructive p-3 text-sm">
          {error}
        </div>
      )}

      {!loading && rows.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="empty">
          No approval requests.
        </p>
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          getRowKey={(row) => row.id}
          loading={loading}
          minWidthClassName="min-w-[640px]"
        />
      )}
    </section>
  );
}
