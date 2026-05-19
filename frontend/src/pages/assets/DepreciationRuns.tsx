/**
 * `/depreciation` — operator-triggered depreciation-run page (Phase 9.10a, #162).
 *
 * Single "Run depreciation for prior month" button. The backend's
 * monthly worker (9.3) handles automation; this UI is the manual
 * re-run / catch-up surface.
 */
import { useState } from "react";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type RunResponse = components["schemas"]["DepreciationRunResponse"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

function previousMonthEnd(): string {
  const today = new Date();
  // Day 0 of current month = last day of prior month.
  const d = new Date(today.getFullYear(), today.getMonth(), 0);
  return d.toISOString().slice(0, 10);
}

export function DepreciationRunsPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [periodEnd, setPeriodEnd] = useState(previousMonthEnd());
  const [submitting, setSubmitting] = useState(false);
  const [lastResult, setLastResult] = useState<RunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onRun(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.post("/api/v1/depreciation-runs", { period_end: periodEnd });
      setLastResult(res.data);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response
        ?.data?.detail;
      setError(typeof detail === "string" ? detail : "Depreciation run failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <header>
        <h1 className="text-xl font-semibold">Depreciation runs</h1>
        <p className="text-sm text-muted-foreground">
          The monthly worker fires at 02:00 UTC on the 1st. Use this form to
          re-run a missed month.
        </p>
      </header>

      {error ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <form className="flex flex-wrap items-end gap-3" onSubmit={onRun} data-testid="run-form">
        <label className="block text-xs">
          Period end
          <Input
            type="date"
            value={periodEnd}
            onChange={(e) => setPeriodEnd(e.target.value)}
            data-testid="run-period-end"
          />
        </label>
        <Button type="submit" disabled={submitting || !canWrite} data-testid="run-submit">
          {submitting ? "Running…" : "Run for this period"}
        </Button>
      </form>

      {lastResult ? (
        <div className="rounded border border-border p-3 text-sm" data-testid="run-result">
          <div className="font-medium">Last run · {lastResult.period_end}</div>
          <div className="text-muted-foreground">
            posted {lastResult.posted_count} · failed {lastResult.failed_count}
          </div>
        </div>
      ) : null}
    </section>
  );
}
