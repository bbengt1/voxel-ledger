import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type RateResponse = components["schemas"]["RateResponse"];
type RateKind = RateResponse["kind"];

const KIND_LABELS: Record<RateKind, string> = {
  labor: "Labor",
  machine: "Machine",
  overhead: "Overhead",
};

const KIND_ORDER: RateKind[] = ["labor", "machine", "overhead"];

export function RatesListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const isOwner = role === "owner";

  const [items, setItems] = useState<RateResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [setDefaultBusy, setSetDefaultBusy] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/api/v1/rates", {
        params: { is_archived: "false" },
      });
      setItems(res.data.items);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Failed to load rates.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function setDefault(rateId: string) {
    setSetDefaultBusy(rateId);
    try {
      await apiClient.post<RateResponse>(`/api/v1/rates/${rateId}/set-default`);
      await load();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Could not set as default.";
      setError(typeof detail === "string" ? detail : "Could not set as default.");
    } finally {
      setSetDefaultBusy(null);
    }
  }

  const groups: Record<RateKind, RateResponse[]> = {
    labor: [],
    machine: [],
    overhead: [],
  };
  for (const r of items) groups[r.kind].push(r);

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Rates</h1>
        {isOwner ? (
          <Button asChild>
            <Link to="/catalog/rates/new">New rate</Link>
          </Button>
        ) : null}
      </header>

      {error ? (
        <div
          role="alert"
          data-testid="rates-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      {loading ? <p className="text-sm text-muted-foreground">Loading…</p> : null}

      {KIND_ORDER.map((kind) => (
        <section
          key={kind}
          aria-labelledby={`rates-${kind}-heading`}
          className="space-y-2"
          data-testid={`rates-section-${kind}`}
        >
          <h2
            id={`rates-${kind}-heading`}
            className="text-sm font-semibold uppercase tracking-wide text-muted-foreground"
          >
            {KIND_LABELS[kind]}
          </h2>
          <table className="w-full table-fixed border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                <th className="py-2 pr-2">Name</th>
                <th className="py-2 pr-2">Value</th>
                <th className="py-2 pr-2">Default</th>
                <th className="py-2 pr-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {groups[kind].length === 0 ? (
                <tr>
                  <td
                    colSpan={4}
                    className="py-3 text-center text-muted-foreground"
                  >
                    No {KIND_LABELS[kind].toLowerCase()} rates.
                  </td>
                </tr>
              ) : (
                groups[kind].map((r) => (
                  <tr
                    key={r.id}
                    className={
                      r.is_default_for_kind
                        ? "border-b border-border/50 bg-accent/30 font-medium"
                        : "border-b border-border/50"
                    }
                    data-testid={`rate-row-${r.id}`}
                  >
                    <td className="py-2 pr-2">
                      <Link
                        to={`/catalog/rates/${r.id}`}
                        className="hover:underline"
                      >
                        {r.name}
                      </Link>
                    </td>
                    <td className="py-2 pr-2">{r.value}</td>
                    <td className="py-2 pr-2">
                      {r.is_default_for_kind ? (
                        <span data-testid={`default-marker-${r.id}`}>
                          Default
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-2 pr-2 text-right">
                      {isOwner && !r.is_default_for_kind ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setDefault(r.id)}
                          disabled={setDefaultBusy === r.id}
                          data-testid={`set-default-${r.id}`}
                        >
                          {setDefaultBusy === r.id
                            ? "Setting…"
                            : "Set as default"}
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>
      ))}
    </section>
  );
}
