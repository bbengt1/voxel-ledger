/**
 * `/tax-remittances` — list tax remittances (Phase 9.10b, #162).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
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

  const columns: DataTableColumn<TaxRemittanceResponse>[] = [
    {
      key: "remittance_number",
      header: "#",
      isPrimary: true,
      cell: (r) => (
        <span className="font-mono text-xs">{r.remittance_number}</span>
      ),
    },
    {
      key: "period",
      header: "Period",
      cell: (r) => (
        <>
          {r.period_start} → {r.period_end}
        </>
      ),
    },
    { key: "paid_on", header: "Paid on", cell: (r) => r.paid_on },
    {
      key: "amount_paid",
      header: "Amount",
      align: "right",
      cell: (r) => r.amount_paid,
    },
    {
      key: "method",
      header: "Method",
      cell: (r) => <span className="text-xs">{r.method}</span>,
    },
    {
      key: "state",
      header: "State",
      cell: (r) => (
        <span className="rounded bg-muted px-1.5 py-0.5 text-xs">{r.state}</span>
      ),
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Tax remittances"
        actions={
          canWrite ? (
            <Button asChild>
              <Link to="/tax-remittances/new">Record remittance</Link>
            </Button>
          ) : null
        }
      />

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(r) => r.id}
        emptyMessage="No remittances yet."
        minWidthClassName="min-w-[640px]"
      />
    </section>
  );
}
