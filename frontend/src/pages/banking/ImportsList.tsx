/**
 * `/banking/imports` — list of bank statement import runs for an account,
 * with a top-of-page "Import statement" entry point.
 */
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { BankAccountPicker } from "@/components/banking/BankAccountPicker";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type Run = components["schemas"]["BankImportRunResponse"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

export function ImportsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const accountId = params.get("account_id") ?? "";

  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function setAccount(id: string) {
    const next = new URLSearchParams(params);
    if (id) next.set("account_id", id);
    else next.delete("account_id");
    setParams(next, { replace: true });
  }

  useEffect(() => {
    if (!accountId) {
      setRuns([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiClient
      .get<{ items: Run[] }>("/api/v1/bank-imports", {
        params: { account_id: accountId },
      })
      .then((res) => {
        if (!cancelled) setRuns(res.data.items ?? []);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load imports.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accountId]);

  return (
    <section className="flex flex-col gap-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Bank statement imports</h1>
        {canWrite ? (
          <Button asChild>
            <Link to="/banking/imports/new">Import statement</Link>
          </Button>
        ) : null}
      </header>

      <label className="block text-sm">
        Account
        <BankAccountPicker
          value={accountId}
          onChange={setAccount}
          data-testid="imports-account-filter"
        />
      </label>

      {error ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Filename</th>
            <th className="py-2 pr-2">Imported at</th>
            <th className="py-2 pr-2 text-right">Rows</th>
            <th className="py-2 pr-2 text-right">Inserted</th>
            <th className="py-2 pr-2 text-right">Duplicates</th>
            <th className="py-2 pr-2 text-right">Errors</th>
          </tr>
        </thead>
        <tbody>
          {!accountId ? (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                Pick an account to see its import history.
              </td>
            </tr>
          ) : loading && runs.length === 0 ? (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                Loading…
              </td>
            </tr>
          ) : runs.length === 0 ? (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                No imports yet for this account.
              </td>
            </tr>
          ) : (
            runs.map((r) => (
              <tr
                key={r.id}
                className="border-b border-border/50"
                data-testid={`run-row-${r.id}`}
              >
                <td className="py-2 pr-2 font-mono text-xs">{r.filename}</td>
                <td className="py-2 pr-2">
                  {new Date(r.imported_at).toLocaleString()}
                </td>
                <td className="py-2 pr-2 text-right">{r.row_count}</td>
                <td className="py-2 pr-2 text-right">{r.inserted_count}</td>
                <td className="py-2 pr-2 text-right">{r.duplicate_count}</td>
                <td className="py-2 pr-2 text-right">{r.error_count}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
