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
import { Button } from "@/components/ui/Button";
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

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Late-fee policies</h1>
        <div className="flex gap-2">
          {canWrite ? (
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
          ) : null}
        </div>
      </header>

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

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Scope</th>
            <th className="py-2 pr-2">Kind</th>
            <th className="py-2 pr-2 text-right">Amount</th>
            <th className="py-2 pr-2 text-right">Grace</th>
            <th className="py-2 pr-2 text-right">Apply after</th>
            <th className="py-2 pr-2">Active</th>
          </tr>
        </thead>
        <tbody>
          {loading && items.length === 0 ? (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                Loading…
              </td>
            </tr>
          ) : items.length === 0 ? (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                No policies.
              </td>
            </tr>
          ) : (
            items.map((p) => (
              <tr
                key={p.id}
                className="border-b border-border/50 hover:bg-accent/30"
                data-testid={`policy-row-${p.id}`}
              >
                <td className="py-2 pr-2">
                  <Link
                    to={`/late-fee-policies/${p.id}`}
                    className="hover:underline"
                  >
                    {p.customer_id ? p.customer_id.slice(0, 8) : "Global"}
                  </Link>
                </td>
                <td className="py-2 pr-2">{p.kind}</td>
                <td className="py-2 pr-2 text-right font-mono">{p.amount}</td>
                <td className="py-2 pr-2 text-right font-mono">
                  {p.grace_period_days}d
                </td>
                <td className="py-2 pr-2 text-right font-mono">
                  {p.apply_after_days}d
                </td>
                <td className="py-2 pr-2">{p.is_active ? "yes" : "no"}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
