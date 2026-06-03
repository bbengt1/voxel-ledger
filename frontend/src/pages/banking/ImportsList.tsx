/**
 * `/banking/imports` — list of bank statement import runs for an account,
 * with a top-of-page "Import statement" entry point.
 */
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { BankAccountPicker } from "@/components/banking/BankAccountPicker";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
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

  const columns: DataTableColumn<Run>[] = [
    {
      key: "filename",
      header: "Filename",
      isPrimary: true,
      cell: (r) => <span className="font-mono text-xs">{r.filename}</span>,
    },
    {
      key: "imported_at",
      header: "Imported at",
      cell: (r) => new Date(r.imported_at).toLocaleString(),
    },
    {
      key: "row_count",
      header: "Rows",
      align: "right",
      cell: (r) => r.row_count,
    },
    {
      key: "inserted_count",
      header: "Inserted",
      align: "right",
      cell: (r) => r.inserted_count,
    },
    {
      key: "duplicate_count",
      header: "Duplicates",
      align: "right",
      cell: (r) => r.duplicate_count,
    },
    {
      key: "error_count",
      header: "Errors",
      align: "right",
      cell: (r) => r.error_count,
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Bank statement imports"
        actions={
          canWrite ? (
            <Button asChild>
              <Link to="/banking/imports/new">Import statement</Link>
            </Button>
          ) : null
        }
      />

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

      <DataTable
        columns={columns}
        rows={runs}
        getRowKey={(r) => r.id}
        loading={loading && runs.length === 0}
        emptyMessage={
          !accountId
            ? "Pick an account to see its import history."
            : "No imports yet for this account."
        }
        minWidthClassName="min-w-[720px]"
      />
    </section>
  );
}
