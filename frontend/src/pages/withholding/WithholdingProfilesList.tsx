/**
 * `/withholding-profiles` — list withholding profiles (Phase 9.10a, #162).
 */
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { FilterBar } from "@/components/ui/FilterBar";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type WithholdingProfileResponse =
  components["schemas"]["WithholdingProfileResponse"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

export function WithholdingProfilesListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [params, setParams] = useSearchParams();
  const search = params.get("search") ?? "";
  const active = params.get("active") ?? "true";

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<WithholdingProfileResponse[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const q: Record<string, string> = {};
    if (search) q["search"] = search;
    if (active === "true") q["active"] = "true";
    if (active === "false") q["active"] = "false";

    api
      .get("/api/v1/withholding-profiles", { params: q })
      .then((res) => setItems(res.data.items))
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } }).response
          ?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load profiles.");
      });
  }, [search, active]);

  const columns: DataTableColumn<WithholdingProfileResponse>[] = [
    {
      key: "code",
      header: "Code",
      isPrimary: true,
      cell: (p) => <span className="font-mono text-xs">{p.code}</span>,
    },
    { key: "name", header: "Name", cell: (p) => p.name },
    { key: "jurisdiction", header: "Jurisdiction", cell: (p) => p.jurisdiction },
    { key: "rate", header: "Rate", align: "right", cell: (p) => p.rate },
    {
      key: "threshold",
      header: "Threshold",
      align: "right",
      cell: (p) => p.threshold_per_year ?? "—",
    },
    { key: "form", header: "Form", cell: (p) => p.form_kind ?? "—" },
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
        title="Withholding profiles"
        actions={
          canWrite ? (
            <Button asChild>
              <Link to="/withholding-profiles/new">New profile</Link>
            </Button>
          ) : null
        }
      />

      <FilterBar columns={2}>
        <label className="block text-xs">
          Active
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={active}
            onChange={(e) => updateParam("active", e.target.value)}
            data-testid="filter-active"
          >
            <option value="true">Active</option>
            <option value="false">Archived</option>
            <option value="">All</option>
          </select>
        </label>
        <label className="block text-xs">
          Search
          <Input
            value={search}
            onChange={(e) => updateParam("search", e.target.value)}
            data-testid="filter-search"
            placeholder="code / name / jurisdiction"
          />
        </label>
      </FilterBar>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(p) => p.id}
        emptyMessage="No withholding profiles yet."
        minWidthClassName="min-w-[760px]"
        rowClassName={() => "hover:bg-accent/30"}
      />
    </section>
  );
}
