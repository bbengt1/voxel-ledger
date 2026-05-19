/**
 * `/tax-profiles` — list tax profiles (Phase 9.10b, #162).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
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

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Tax profiles</h1>
        {canWrite ? (
          <Button asChild>
            <Link to="/tax-profiles/new">New profile</Link>
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
            <th className="py-2 pr-2">Code</th>
            <th className="py-2 pr-2">Name</th>
            <th className="py-2 pr-2">Jurisdiction</th>
            <th className="py-2 pr-2">Reverse charge?</th>
            <th className="py-2 pr-2">Active</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <tr>
              <td colSpan={5} className="py-4 text-center text-muted-foreground">
                No tax profiles yet.
              </td>
            </tr>
          ) : (
            items.map((p) => (
              <tr key={p.id} className="border-b border-border/50 hover:bg-accent/30" data-testid={`tax-profile-row-${p.id}`}>
                <td className="py-2 pr-2 font-mono text-xs">
                  <Link to={`/tax-profiles/${p.id}`} className="hover:underline">
                    {p.code}
                  </Link>
                </td>
                <td className="py-2 pr-2">{p.name}</td>
                <td className="py-2 pr-2">{p.jurisdiction}</td>
                <td className="py-2 pr-2">{p.is_reverse_charge ? "yes" : "no"}</td>
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
