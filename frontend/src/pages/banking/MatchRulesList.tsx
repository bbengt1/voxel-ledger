/**
 * `/banking/match-rules` — list of auto-match rules with a "Run auto-match
 * now" trigger and per-rule deactivate.
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

type Rule = components["schemas"]["BankMatchRuleResponse"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

export function MatchRulesListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [items, setItems] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runMessage, setRunMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/api/v1/bank-match-rules");
      setItems(res.data.items);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to load rules.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function runNow() {
    setRunMessage(null);
    try {
      const res = await apiClient.post<{
        matched_count?: number;
        count?: number;
      }>("/api/v1/bank-match-rules/run-now");
      const data = (res.data ?? {}) as Record<string, unknown>;
      const n =
        (typeof data["matched_count"] === "number"
          ? (data["matched_count"] as number)
          : null) ??
        (typeof data["count"] === "number" ? (data["count"] as number) : null);
      setRunMessage(
        n === null ? "Auto-match run complete." : `Matched ${n} transactions.`,
      );
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Run-now failed.");
    }
  }

  async function deactivate(id: string) {
    try {
      await apiClient.post(`/api/v1/bank-match-rules/${id}/deactivate`);
      await load();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not deactivate.");
    }
  }

  const columns: DataTableColumn<Rule>[] = [
    {
      key: "priority",
      header: "Priority",
      isPrimary: true,
      cell: (r) => (
        <span data-testid={`rule-row-${r.id}`}>{r.priority}</span>
      ),
    },
    {
      key: "scope",
      header: "Scope",
      cell: (r) => (r.account_id ? "account-scoped" : "global"),
    },
    {
      key: "match",
      header: "Match",
      cell: (r) => (
        <span className="text-xs">
          {r.match_kind}({r.match_field}) ={" "}
          <span className="font-mono">{r.match_value}</span>
        </span>
      ),
    },
    {
      key: "action",
      header: "Action",
      cell: (r) => <span className="text-xs">{r.action_kind}</span>,
    },
    {
      key: "is_active",
      header: "Active",
      cell: (r) => (r.is_active ? "yes" : "no"),
    },
    {
      key: "actions",
      header: "Actions",
      align: "right",
      cardFullWidth: true,
      cell: (r) =>
        canWrite && r.is_active ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => void deactivate(r.id)}
            data-testid={`rule-deactivate-${r.id}`}
          >
            Deactivate
          </Button>
        ) : null,
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Bank match rules"
        actions={
          <>
            {canWrite ? (
              <Button
                variant="outline"
                onClick={() => void runNow()}
                data-testid="run-now-btn"
              >
                Run auto-match now
              </Button>
            ) : null}
            {canWrite ? (
              <Button asChild>
                <Link to="/banking/match-rules/new">New rule</Link>
              </Button>
            ) : null}
          </>
        }
      />

      {runMessage ? (
        <p className="text-sm text-emerald-700" data-testid="run-now-message">
          {runMessage}
        </p>
      ) : null}

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
        getRowKey={(r) => r.id}
        loading={loading && items.length === 0}
        emptyMessage="No rules yet."
        minWidthClassName="min-w-[720px]"
      />
    </section>
  );
}
