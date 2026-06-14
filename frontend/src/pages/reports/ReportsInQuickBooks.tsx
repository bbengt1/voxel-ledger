/**
 * `/reports/quickbooks` — financial reports moved to QuickBooks (#318 5d).
 *
 * QBO replace-mode (epic #312): the in-app GL reports (income statement,
 * balance sheet, cash flow, trial balance, GL detail, AR/AP aging, budget
 * variance, divisions comparison, tax liability) were removed — QuickBooks is
 * the system of record and its reporting replaces them. The old report routes
 * all land here so bookmarks explain themselves instead of 404ing.
 *
 * The link target comes from ``GET /api/v1/reports/quickbooks-link`` (generic
 * QBO web-app URL; phase-0 decision: no report deep-links).
 */
import { useEffect, useState } from "react";

import { api } from "@/api/typed";
import { Button } from "@/components/ui/Button";

const REPORTS_MOVED = [
  "Income statement",
  "Balance sheet",
  "Cash flow",
  "Trial balance",
  "General ledger detail",
  "AR aging",
  "AP aging",
  "Budget vs actual",
  "Divisions comparison",
  "Tax liability",
];

export function ReportsInQuickBooksPage() {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    api
      .get("/api/v1/reports/quickbooks-link")
      .then((res) => setUrl((res.data as { url: string }).url))
      .catch(() => setUrl(null));
  }, []);

  return (
    <section data-testid="reports-in-quickbooks" className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          Financial reports live in QuickBooks
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          QuickBooks Online is the system of record for the books. The
          financial reports below are no longer generated in this app — run
          them in QuickBooks.
        </p>
      </header>

      <ul className="list-disc pl-6 text-sm text-muted-foreground">
        {REPORTS_MOVED.map((name) => (
          <li key={name}>{name}</li>
        ))}
      </ul>

      <div>
        <Button
          type="button"
          onClick={() => {
            if (url) window.open(url, "_blank", "noopener,noreferrer");
          }}
          disabled={!url}
          data-testid="open-quickbooks"
        >
          Open QuickBooks
        </Button>
      </div>

      <p className="text-xs text-muted-foreground">
        Operational reports (sales by period, inventory valuation, withholding
        1099) are still available in this app under Reports.
      </p>
    </section>
  );
}
