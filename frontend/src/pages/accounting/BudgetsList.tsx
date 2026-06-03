/**
 * Budgets list with per-account/division variance display.
 *
 * Period selector defaults to the period containing today; if none, the
 * most recent closed one; if none, the most recent overall.
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import {
  AccountPicker,
  type AccountOption,
} from "@/components/accounting/AccountPicker";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type AccountingPeriodResponse =
  components["schemas"]["AccountingPeriodResponse"];
type DivisionResponse = components["schemas"]["DivisionResponse"];
type BudgetVarianceRow = components["schemas"]["BudgetVarianceRow"];

const WRITE_ROLES = new Set(["owner", "bookkeeper"]);

function pickDefaultPeriodId(
  periods: AccountingPeriodResponse[],
): string | null {
  if (periods.length === 0) return null;
  const today = new Date().toISOString().slice(0, 10);
  const containing = periods.find(
    (p) => p.start_date <= today && today <= p.end_date,
  );
  if (containing) return containing.id;
  const closed = periods.filter((p) => p.state === "closed");
  if (closed.length > 0) return closed[0]!.id;
  return periods[0]!.id;
}

function isFavorable(row: BudgetVarianceRow): "fav" | "unfav" | "zero" {
  const v = Number(row.variance);
  if (Math.abs(v) < 1e-9) return "zero";
  // For revenue accounts, exceeding budget (actual > budget) is favorable.
  // For expense accounts, exceeding budget is unfavorable.
  // Variance sign convention: backend returns budget - actual (or similar).
  // We rely on row.account_type to color it.
  if (row.account_type === "revenue") {
    return v <= 0 ? "fav" : "unfav";
  }
  return v >= 0 ? "fav" : "unfav";
}

const VARIANCE_COLOR: Record<"fav" | "unfav" | "zero", string> = {
  fav: "text-emerald-600 dark:text-emerald-400",
  unfav: "text-destructive",
  zero: "text-muted-foreground",
};

export function BudgetsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = !!role && WRITE_ROLES.has(role);

  const [periods, setPeriods] = useState<AccountingPeriodResponse[]>([]);
  const [periodId, setPeriodId] = useState<string>("");
  const [rows, setRows] = useState<BudgetVarianceRow[]>([]);
  const [divisions, setDivisions] = useState<DivisionResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [newOpen, setNewOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.get("/api/v1/accounting/periods"),
      api.get("/api/v1/accounting/divisions", {
        params: { is_archived: "false" },
      }),
    ])
      .then(([periodsRes, divsRes]) => {
        if (cancelled) return;
        setPeriods(periodsRes.data.items);
        setDivisions(divsRes.data.items);
        setPeriodId((cur) =>
          cur ? cur : pickDefaultPeriodId(periodsRes.data.items) ?? "",
        );
      })
      .catch(() => {
        if (!cancelled) {
          setPeriods([]);
          setDivisions([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!periodId) {
      setRows([]);
      return;
    }
    let cancelled = false;
    setError(null);
    api
      .get("/api/v1/accounting/budgets/variance", {
        params: { period_id: periodId },
      })
      .then((res) => {
        if (cancelled) return;
        setRows(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load budgets.";
        setError(msg);
      });
    return () => {
      cancelled = true;
    };
  }, [periodId, reloadKey]);

  const columns: DataTableColumn<BudgetVarianceRow>[] = [
    {
      key: "account",
      header: "Account",
      isPrimary: true,
      cell: (row) => (
        <>
          <span className="font-mono text-xs">{row.account_code}</span>{" "}
          {row.account_name}
        </>
      ),
    },
    {
      key: "division",
      header: "Division",
      cell: (row) => (
        <span className="text-xs">{row.division_name ?? "All"}</span>
      ),
    },
    {
      key: "budget",
      header: "Budget",
      align: "right",
      cell: (row) => (
        <span className="tabular-nums">
          {Number(row.budget_amount).toFixed(2)}
        </span>
      ),
    },
    {
      key: "actual",
      header: "Actual",
      align: "right",
      cell: (row) => (
        <span className="tabular-nums">
          {Number(row.actual_amount).toFixed(2)}
        </span>
      ),
    },
    {
      key: "variance",
      header: "Variance",
      align: "right",
      cell: (row) => (
        <span
          className={"tabular-nums " + VARIANCE_COLOR[isFavorable(row)]}
          data-testid={`variance-${row.account_id}`}
        >
          {Number(row.variance).toFixed(2)}
        </span>
      ),
    },
    {
      key: "pct",
      header: "%",
      align: "right",
      cell: (row) => (
        <span className="tabular-nums text-xs">{row.variance_pct}%</span>
      ),
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Budgets"
        actions={
          <div className="flex gap-2">
            <Button asChild variant="outline">
              <Link
                to={`/accounting/budgets/variance${
                  periodId ? `?period_id=${periodId}` : ""
                }`}
              >
                Variance report
              </Link>
            </Button>
            {canWrite ? (
              <Button onClick={() => setNewOpen(true)} data-testid="open-new-budget">
                New budget
              </Button>
            ) : null}
          </div>
        }
      />

      <label className="flex flex-col gap-1 text-xs font-medium">
        Period
        <select
          className="h-9 w-64 rounded-md border border-input bg-background px-2 text-sm"
          value={periodId}
          onChange={(e) => setPeriodId(e.target.value)}
          data-testid="period-select"
        >
          {periods.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.state})
            </option>
          ))}
        </select>
      </label>

      {error ? (
        <div role="alert" data-testid="budgets-error" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={rows}
        getRowKey={(row) => `${row.account_id}-${row.division_id ?? "all"}`}
        emptyMessage="No budgets for this period."
        minWidthClassName="min-w-[640px]"
      />

      <NewBudgetDialog
        open={newOpen}
        onClose={() => setNewOpen(false)}
        onCreated={() => {
          setNewOpen(false);
          setReloadKey((k) => k + 1);
        }}
        periodId={periodId}
        divisions={divisions}
      />
    </section>
  );
}

function NewBudgetDialog({
  open,
  onClose,
  onCreated,
  periodId,
  divisions,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  periodId: string;
  divisions: DivisionResponse[];
}) {
  const [account, setAccount] = useState<AccountOption | null>(null);
  const [divisionId, setDivisionId] = useState<string>("");
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setAccount(null);
      setDivisionId("");
      setAmount("");
      setError(null);
    }
  }, [open]);

  const submitDisabled = useMemo(() => {
    if (busy) return true;
    if (!account) return true;
    if (!periodId) return true;
    const n = Number(amount);
    if (!Number.isFinite(n) || n < 0) return true;
    return false;
  }, [busy, account, periodId, amount]);

  async function submit() {
    if (!account) return;
    setBusy(true);
    setError(null);
    try {
      await apiClient.post("/api/v1/accounting/budgets", {
        account_id: account.id,
        period_id: periodId,
        division_id: divisionId || null,
        amount,
      });
      onCreated();
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Create failed.";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => (!v ? onClose() : undefined)}>
      <DialogContent data-testid="new-budget-dialog">
        <DialogTitle>New budget</DialogTitle>
        <div className="mt-3 flex flex-col gap-2">
          {error ? (
            <div
              role="alert"
              data-testid="new-budget-error"
              className="rounded border border-destructive bg-destructive/10 p-2 text-xs text-destructive"
            >
              {error}
            </div>
          ) : null}
          <label className="flex flex-col gap-1 text-xs">
            Account
            <AccountPicker
              value={account}
              onChange={setAccount}
              data-testid="new-budget-account"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            Division
            <select
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              value={divisionId}
              onChange={(e) => setDivisionId(e.target.value)}
              data-testid="new-budget-division"
            >
              <option value="">All divisions</option>
              {divisions.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.code} — {d.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs">
            Amount
            <Input
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              data-testid="new-budget-amount"
            />
          </label>
          <div className="mt-2 flex justify-end gap-2">
            <Button variant="outline" onClick={onClose} disabled={busy}>
              Cancel
            </Button>
            <Button
              onClick={submit}
              disabled={submitDisabled}
              data-testid="submit-new-budget"
            >
              Create
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
