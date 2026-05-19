/**
 * `/withholding-profiles` — list withholding profiles (Phase 9.10a, #162).
 */
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
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

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Withholding profiles</h1>
        {canWrite ? (
          <Button asChild>
            <Link to="/withholding-profiles/new">New profile</Link>
          </Button>
        ) : null}
      </header>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
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
      </div>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Code</th>
            <th className="py-2 pr-2">Name</th>
            <th className="py-2 pr-2">Jurisdiction</th>
            <th className="py-2 pr-2">Rate</th>
            <th className="py-2 pr-2">Threshold</th>
            <th className="py-2 pr-2">Form</th>
            <th className="py-2 pr-2">Active</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <tr>
              <td colSpan={7} className="py-4 text-center text-muted-foreground">
                No withholding profiles yet.
              </td>
            </tr>
          ) : (
            items.map((p) => (
              <tr
                key={p.id}
                className="border-b border-border/50 hover:bg-accent/30"
                data-testid={`withholding-row-${p.id}`}
              >
                <td className="py-2 pr-2 font-mono text-xs">{p.code}</td>
                <td className="py-2 pr-2">{p.name}</td>
                <td className="py-2 pr-2">{p.jurisdiction}</td>
                <td className="py-2 pr-2">{p.rate}</td>
                <td className="py-2 pr-2">{p.threshold_per_year ?? "—"}</td>
                <td className="py-2 pr-2">{p.form_kind ?? "—"}</td>
                <td className="py-2 pr-2">
                  <span className="rounded bg-muted px-1.5 py-0.5 text-xs">
                    {p.is_active ? "active" : "archived"}
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
