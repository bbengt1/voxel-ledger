/**
 * `/late-fee-policies` — list of late-fee policies (global + per-customer)
 * with an "Apply now" button that triggers an operator sweep across all
 * applicable invoices.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { useAuthStore } from "@/store/useAuthStore";

type LateFeePolicyResponse = components["schemas"]["LateFeePolicyResponse"];

const WRITE_ROLES: readonly string[] = ["owner", "bookkeeper"];

export function LateFeePoliciesListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? WRITE_ROLES.includes(role) : false;

  const [items, setItems] = useState<LateFeePolicyResponse[]>([]);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/api/v1/late-fee-policies", {
        params: includeInactive ? { include_inactive: true } : {},
      });
      setItems(res.data.items);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : "Failed to load policies.",
      );
    } finally {
      setLoading(false);
    }
  }, [includeInactive]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  async function applyNow() {
    if (!window.confirm("Sweep all eligible invoices and apply late fees?"))
      return;
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      await apiClient.post("/api/v1/late-fee-policies/apply-now", null);
      setNotice("Late-fee sweep enqueued.");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not apply.");
    } finally {
      setBusy(false);
    }
  }

  const columns: DataTableColumn<LateFeePolicyResponse>[] = [
    {
      key: "scope",
      header: "Scope",
      isPrimary: true,
      cell: (p) => (
        <Link to={`/late-fee-policies/${p.id}`} className="hover:underline">
          {p.customer_id ? p.customer_id.slice(0, 8) : "Global"}
        </Link>
      ),
    },
    { key: "kind", header: "Kind", cell: (p) => p.kind },
    {
      key: "amount",
      header: "Amount",
      align: "right",
      cell: (p) => <span className="font-mono">{p.amount}</span>,
    },
    {
      key: "grace",
      header: "Grace",
      align: "right",
      cell: (p) => <span className="font-mono">{p.grace_period_days}d</span>,
    },
    {
      key: "apply_after",
      header: "Apply after",
      align: "right",
      cell: (p) => <span className="font-mono">{p.apply_after_days}d</span>,
    },
    { key: "active", header: "Active", cell: (p) => (p.is_active ? "yes" : "no") },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Late-fee policies"
        actions={
          canWrite ? (
            <>
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => void applyNow()}
                data-testid="apply-now-btn"
              >
                {busy ? "Applying…" : "Apply now"}
              </Button>
              <Button asChild>
                <Link to="/late-fee-policies/new">New policy</Link>
              </Button>
            </>
          ) : null
        }
      />

      <label className="flex items-center gap-2 text-xs">
        <input
          type="checkbox"
          checked={includeInactive}
          onChange={(e) => setIncludeInactive(e.target.checked)}
          data-testid="filter-include-inactive"
        />
        Include inactive
      </label>

      {error ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}
      {notice ? (
        <p
          role="status"
          className="rounded border border-border bg-muted/30 p-3 text-sm"
          data-testid="policies-notice"
        >
          {notice}
        </p>
      ) : null}

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(p) => p.id}
        loading={loading && items.length === 0}
        emptyMessage="No policies."
        minWidthClassName="min-w-[640px]"
        rowClassName={() => "hover:bg-accent/30"}
      />
    </section>
  );
}
