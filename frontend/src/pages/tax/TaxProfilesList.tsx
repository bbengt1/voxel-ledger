/**
 * `/tax-profiles` — list tax profiles (Phase 9.10b, #162).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { useAuthStore } from "@/store/useAuthStore";

type TaxProfileResponse = components["schemas"]["TaxProfileResponse"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

export function TaxProfilesListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [items, setItems] = useState<TaxProfileResponse[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get("/api/v1/tax-profiles")
      .then((res) => setItems(res.data.items))
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } }).response
          ?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load tax profiles.");
      });
  }, []);

  const columns: DataTableColumn<TaxProfileResponse>[] = [
    {
      key: "code",
      header: "Code",
      isPrimary: true,
      cell: (p) => (
        <Link
          to={`/tax-profiles/${p.id}`}
          className="font-mono text-xs hover:underline"
        >
          {p.code}
        </Link>
      ),
    },
    { key: "name", header: "Name", cell: (p) => p.name },
    { key: "jurisdiction", header: "Jurisdiction", cell: (p) => p.jurisdiction },
    {
      key: "is_reverse_charge",
      header: "Reverse charge?",
      cell: (p) => (p.is_reverse_charge ? "yes" : "no"),
    },
    {
      key: "is_active",
      header: "Active",
      cell: (p) => (
        <span className="rounded bg-muted px-1.5 py-0.5 text-xs">
          {p.is_active ? "active" : "archived"}
        </span>
      ),
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Tax profiles"
        actions={
          canWrite ? (
            <Button asChild>
              <Link to="/tax-profiles/new">New profile</Link>
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
        getRowKey={(p) => p.id}
        emptyMessage="No tax profiles yet."
        minWidthClassName="min-w-[640px]"
        rowClassName={() => "hover:bg-accent/30"}
      />
    </section>
  );
}
