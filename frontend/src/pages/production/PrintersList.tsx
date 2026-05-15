import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type PrinterResponse = components["schemas"]["PrinterResponse"];

const CAN_WRITE_ROLES = ["owner", "production"] as const;

export function PrintersListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role
    ? (CAN_WRITE_ROLES as readonly string[]).includes(role)
    : false;

  const [items, setItems] = useState<PrinterResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiClient
      .get<components["schemas"]["PrinterListResponse"]>("/api/v1/printers", {
        params: { is_archived: false },
      })
      .then((res) => {
        if (cancelled) return;
        setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load printers.";
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
        <h1 className="text-xl font-semibold">Printers</h1>
        {canWrite ? (
          <Button asChild>
            <Link to="/production/printers/new">New printer</Link>
          </Button>
        ) : null}
      </header>

      {error ? (
        <div
          role="alert"
          data-testid="printers-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Slug</th>
            <th className="py-2 pr-2">Name</th>
            <th className="py-2 pr-2">Type</th>
            <th className="py-2 pr-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {loading && items.length === 0 ? (
            <tr>
              <td colSpan={4} className="py-4 text-center text-muted-foreground">
                Loading...
              </td>
            </tr>
          ) : items.length === 0 ? (
            <tr>
              <td colSpan={4} className="py-4 text-center text-muted-foreground">
                No printers configured yet.
              </td>
            </tr>
          ) : (
            items.map((p) => (
              <tr key={p.id} className="border-b border-border/50">
                <td className="py-2 pr-2 font-mono text-xs">
                  <Link
                    to={`/production/printers/${p.id}`}
                    className="hover:underline"
                  >
                    {p.slug}
                  </Link>
                </td>
                <td className="py-2 pr-2">{p.name}</td>
                <td className="py-2 pr-2">{p.printer_type}</td>
                <td className="py-2 pr-2">
                  {p.is_archived ? "Archived" : "Active"}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
