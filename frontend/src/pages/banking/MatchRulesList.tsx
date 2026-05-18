/**
 * `/banking/match-rules` — list of auto-match rules with a "Run auto-match
 * now" trigger and per-rule deactivate.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
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

  return (
    <section className="flex flex-col gap-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Bank match rules</h1>
        <div className="flex gap-2">
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
        </div>
      </header>

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

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Priority</th>
            <th className="py-2 pr-2">Scope</th>
            <th className="py-2 pr-2">Match</th>
            <th className="py-2 pr-2">Action</th>
            <th className="py-2 pr-2">Active</th>
            <th className="py-2 pr-2 text-right">Actions</th>
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
                No rules yet.
              </td>
            </tr>
          ) : (
            items.map((r) => (
              <tr
                key={r.id}
                className="border-b border-border/50"
                data-testid={`rule-row-${r.id}`}
              >
                <td className="py-2 pr-2">{r.priority}</td>
                <td className="py-2 pr-2">
                  {r.account_id ? "account-scoped" : "global"}
                </td>
                <td className="py-2 pr-2 text-xs">
                  {r.match_kind}({r.match_field}) ={" "}
                  <span className="font-mono">{r.match_value}</span>
                </td>
                <td className="py-2 pr-2 text-xs">{r.action_kind}</td>
                <td className="py-2 pr-2">{r.is_active ? "yes" : "no"}</td>
                <td className="py-2 pr-2 text-right">
                  {canWrite && r.is_active ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void deactivate(r.id)}
                      data-testid={`rule-deactivate-${r.id}`}
                    >
                      Deactivate
                    </Button>
                  ) : null}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
