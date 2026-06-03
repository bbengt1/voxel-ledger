import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
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

  const columns: DataTableColumn<RateResponse>[] = [
    {
      key: "name",
      header: "Name",
      isPrimary: true,
      cell: (r) => (
        <Link to={`/catalog/rates/${r.id}`} className="hover:underline">
          {r.name}
        </Link>
      ),
    },
    { key: "value", header: "Value", align: "right", cell: (r) => r.value },
    {
      key: "default",
      header: "Default",
      cell: (r) =>
        r.is_default_for_kind ? (
          <span data-testid={`default-marker-${r.id}`}>Default</span>
        ) : (
          "—"
        ),
    },
    {
      key: "actions",
      header: "Actions",
      align: "right",
      cardFullWidth: true,
      cell: (r) =>
        isOwner && !r.is_default_for_kind ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => setDefault(r.id)}
            disabled={setDefaultBusy === r.id}
            data-testid={`set-default-${r.id}`}
          >
            {setDefaultBusy === r.id ? "Setting…" : "Set as default"}
          </Button>
        ) : null,
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Rates"
        actions={
          isOwner ? (
            <Button asChild>
              <Link to="/catalog/rates/new">New rate</Link>
            </Button>
          ) : null
        }
      />

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
          <DataTable
            columns={columns}
            rows={groups[kind]}
            getRowKey={(r) => r.id}
            emptyMessage={`No ${KIND_LABELS[kind].toLowerCase()} rates.`}
            minWidthClassName="min-w-[480px]"
            rowClassName={(r) =>
              r.is_default_for_kind ? "bg-accent/30 font-medium" : undefined
            }
          />
        </section>
      ))}
    </section>
  );
}
