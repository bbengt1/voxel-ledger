/**
 * `/tax-remittances` — list tax remittances (Phase 9.10b, #162).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type TaxRemittanceResponse = components["schemas"]["TaxRemittanceResponse"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

export function TaxRemittancesListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [items, setItems] = useState<TaxRemittanceResponse[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get("/api/v1/tax-remittances")
      .then((res) => setItems(res.data.items))
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } }).response
          ?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load remittances.");
      });
  }, []);

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Tax remittances</h1>
        {canWrite ? (
          <Button asChild>
            <Link to="/tax-remittances/new">Record remittance</Link>
          </Button>
        ) : null}
      </header>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">#</th>
            <th className="py-2 pr-2">Period</th>
            <th className="py-2 pr-2">Paid on</th>
            <th className="py-2 pr-2">Amount</th>
            <th className="py-2 pr-2">Method</th>
            <th className="py-2 pr-2">State</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                No remittances yet.
              </td>
            </tr>
          ) : (
            items.map((r) => (
              <tr key={r.id} className="border-b border-border/50">
                <td className="py-2 pr-2 font-mono text-xs">{r.remittance_number}</td>
                <td className="py-2 pr-2">
                  {r.period_start} → {r.period_end}
                </td>
                <td className="py-2 pr-2">{r.paid_on}</td>
                <td className="py-2 pr-2">{r.amount_paid}</td>
                <td className="py-2 pr-2 text-xs">{r.method}</td>
                <td className="py-2 pr-2">
                  <span className="rounded bg-muted px-1.5 py-0.5 text-xs">
                    {r.state}
                  </span>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
