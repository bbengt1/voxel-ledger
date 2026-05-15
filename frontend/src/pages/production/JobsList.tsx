import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";

type JobResponse = components["schemas"]["JobResponse"];

export function JobsListPage() {
  const [items, setItems] = useState<JobResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiClient
      .get<components["schemas"]["JobListResponse"]>("/api/v1/jobs")
      .then((res) => {
        if (cancelled) return;
        setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load jobs.";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Jobs</h1>
        <p className="text-sm text-muted-foreground">
          Composer lands in a follow-up issue (#82).
        </p>
      </header>

      {error ? (
        <div
          role="alert"
          data-testid="jobs-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Job #</th>
            <th className="py-2 pr-2">State</th>
            <th className="py-2 pr-2">Qty</th>
            <th className="py-2 pr-2">Pieces</th>
            <th className="py-2 pr-2">Due</th>
          </tr>
        </thead>
        <tbody>
          {loading && items.length === 0 ? (
            <tr>
              <td colSpan={5} className="py-4 text-center text-muted-foreground">
                Loading...
              </td>
            </tr>
          ) : items.length === 0 ? (
            <tr>
              <td colSpan={5} className="py-4 text-center text-muted-foreground">
                No jobs yet.
              </td>
            </tr>
          ) : (
            items.map((j) => (
              <tr key={j.id} className="border-b border-border/50">
                <td className="py-2 pr-2 font-mono text-xs">{j.job_number}</td>
                <td className="py-2 pr-2">{j.state}</td>
                <td className="py-2 pr-2">{j.quantity_ordered}</td>
                <td className="py-2 pr-2">{j.pieces_produced}</td>
                <td className="py-2 pr-2">
                  {j.due_at ? new Date(j.due_at).toLocaleDateString() : "—"}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
