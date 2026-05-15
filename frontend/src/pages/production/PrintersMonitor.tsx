/**
 * `/production/printers` — printer monitor grid. Replaces the Phase 5.1
 * stub table with one card per active printer. Each card owns its own
 * state polling + snapshot refresh and handles the 503 warmup contract
 * (see PrinterStateCard).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PrinterStateCard } from "@/components/production/PrinterStateCard";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type PrinterResponse = components["schemas"]["PrinterResponse"];

const CAN_WRITE: readonly string[] = ["owner", "production"];

export function PrintersMonitorPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [items, setItems] = useState<PrinterResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/printers", { params: { is_archived: "false" } })
      .then((res) => {
        if (!cancelled) setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setError(
          typeof detail === "string" ? detail : "Failed to load printers.",
        );
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

      {loading && items.length === 0 ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No printers configured yet.
        </p>
      ) : (
        <div
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
          data-testid="printers-grid"
        >
          {items.map((p) => (
            <PrinterStateCard key={p.id} printer={p} />
          ))}
        </div>
      )}
    </section>
  );
}
