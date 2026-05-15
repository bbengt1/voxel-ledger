/**
 * Approval-queue list view (Phase 4.4).
 *
 * Owner and bookkeeper roles see every request the backend returns;
 * other roles see only their own requests — the API scopes the query
 * for us, so the page simply renders ``GET /api/v1/approvals``.
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";

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

  return (
    <section className="flex flex-col gap-4">
      <header className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Approvals</h1>
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
      </header>

      {error && (
        <div role="alert" className="rounded border border-destructive p-3 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="empty">
          No approval requests.
        </p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th className="py-2">Type</th>
              <th>Subject</th>
              <th>State</th>
              <th>Threshold</th>
              <th>Requested</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-border">
                <td className="py-2">{row.request_type}</td>
                <td>
                  {row.subject_kind}:{row.subject_id.slice(0, 8)}
                </td>
                <td>{row.state}</td>
                <td>{row.threshold_amount ?? "—"}</td>
                <td>{new Date(row.requested_at).toLocaleString()}</td>
                <td>
                  <Link
                    to={`/approvals/${row.id}`}
                    className="text-primary underline"
                  >
                    Open
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
