/**
 * `/` — dashboard home (Phase 10.8b, #183; GL tiles retired in #318 5d).
 *
 * Top row of KPI tiles fed by ``GET /api/v1/dashboard/kpis`` and an
 * AI-insights tile for ``sales_trend`` with a Refresh button that
 * POSTs a new request and polls until ready. The GL-derived tiles
 * (cash on hand, net income) and the trailing-12-month net-income
 * chart moved to QuickBooks with the rest of financial reporting
 * (QBO replace-mode, epic #312).
 *
 * Keeps the legacy ``home-screen`` test id on the outer card so the
 * App.test.tsx smoke covers the new layout too.
 */
import { useCallback, useEffect, useState } from "react";

import { Link } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type DashboardKpis = components["schemas"]["DashboardKpisResponse"];
type AiInsight = components["schemas"]["AiInsightSummaryResponse"];

const CAN_REQUEST_INSIGHTS: readonly string[] = ["owner", "bookkeeper"];

function isoDay(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function Tile({
  label,
  value,
  subtle,
}: {
  label: string;
  value: string | number;
  subtle?: string | undefined;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {subtle ? (
        <div className="text-xs text-muted-foreground mt-1">{subtle}</div>
      ) : null}
    </div>
  );
}

export function HomePage() {
  const user = useAuthStore((s) => s.user);
  const canRequest = user?.role
    ? CAN_REQUEST_INSIGHTS.includes(user.role)
    : false;

  const [kpis, setKpis] = useState<DashboardKpis | null>(null);
  const [insight, setInsight] = useState<AiInsight | null>(null);
  const [insightPolling, setInsightPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // KPI tiles.
  useEffect(() => {
    api
      .get("/api/v1/dashboard/kpis")
      .then((res) => setKpis(res.data))
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load KPIs.");
      });
  }, []);

  // AI insight tile.
  const loadLatestInsight = useCallback(() => {
    api
      .get("/api/v1/dashboard/ai-insights/latest", {
        params: { scope: "sales_trend" },
      })
      .then((res) => setInsight(res.data ?? null))
      .catch(() => {
        setInsight(null);
      });
  }, []);

  useEffect(() => {
    loadLatestInsight();
  }, [loadLatestInsight]);

  async function refreshInsight() {
    if (!canRequest) return;
    setInsightPolling(true);
    const today = new Date();
    const start = new Date(today.getFullYear(), today.getMonth() - 2, 1);
    try {
      await api.post("/api/v1/dashboard/ai-insights/requests", {
        scope: "sales_trend",
        period_start: isoDay(start),
        period_end: isoDay(today),
      });
      // Poll a handful of times — the worker fires every 15 min in
      // production, but the deterministic provider used in dev is
      // instant once the worker runs.
      for (let i = 0; i < 5; i += 1) {
        await new Promise((r) => setTimeout(r, 800));
        const res = await api.get("/api/v1/dashboard/ai-insights/latest", {
          params: { scope: "sales_trend" },
        });
        if (res.data && res.data.status === "ready") {
          setInsight(res.data);
          break;
        }
      }
    } finally {
      setInsightPolling(false);
    }
  }

  return (
    <section data-testid="home-screen" className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        {user ? (
          <p className="text-xs text-muted-foreground">
            Logged in as {user.email} ({user.role}).
          </p>
        ) : null}
      </header>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {kpis ? (
        <div
          className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4"
          data-testid="kpi-tiles"
        >
          <Tile
            label="Cash on hand"
            value={kpis.cash_on_hand ?? "—"}
            subtle={kpis.cash_on_hand == null ? "In QuickBooks" : undefined}
          />
          <Tile
            label="Accounts receivable"
            value={kpis.accounts_receivable}
            subtle={`${kpis.overdue_invoice_count} overdue`}
          />
          <Tile
            label="Accounts payable"
            value={kpis.accounts_payable}
            subtle={`${kpis.overdue_bill_count} overdue`}
          />
          <Tile label="Low-stock alerts" value={kpis.low_stock_alert_count} />
          <Tile
            label="Net income (MTD)"
            value={kpis.net_income_mtd ?? "—"}
            subtle={kpis.net_income_mtd == null ? "In QuickBooks" : undefined}
          />
          <Tile
            label="Net income (YTD)"
            value={kpis.net_income_ytd ?? "—"}
            subtle={kpis.net_income_ytd == null ? "In QuickBooks" : undefined}
          />
        </div>
      ) : (
        <p className="text-muted-foreground">Loading KPIs…</p>
      )}

      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-medium">Financial reporting</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Financial statements (income statement, balance sheet, cash flow,
          trial balance, aging) live in QuickBooks now.{" "}
          <Link to="/reports/quickbooks" className="text-primary underline">
            Open reports in QuickBooks
          </Link>
        </p>
      </section>

      <section
        className="rounded-lg border border-border bg-card p-4"
        data-testid="ai-insights-tile"
      >
        <header className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-medium">AI insight — sales trend</h2>
          {canRequest ? (
            <Button
              type="button"
              variant="ghost"
              onClick={refreshInsight}
              disabled={insightPolling}
              data-testid="ai-insights-refresh"
            >
              {insightPolling ? "Refreshing…" : "Refresh"}
            </Button>
          ) : null}
        </header>
        {insight ? (
          <>
            <p className="mt-2 whitespace-pre-line text-sm" data-testid="ai-insights-narrative">
              {insight.narrative}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              Model: {insight.model ?? "—"} · period {insight.period_start} →{" "}
              {insight.period_end}
            </p>
          </>
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">
            No insight ready yet. {canRequest ? "Click Refresh to request one." : null}
          </p>
        )}
      </section>
    </section>
  );
}
