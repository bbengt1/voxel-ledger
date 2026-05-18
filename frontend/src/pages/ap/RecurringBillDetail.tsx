/**
 * `/recurring-bills/:id` — read-only template detail with pause /
 * resume / cancel / materialize-now state action bar. Mirrors
 * RecurringDetail (AR side).
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type RecurringBillTemplateResponse =
  components["schemas"]["RecurringBillTemplateResponse"];

const WRITE_ROLES: readonly string[] = ["owner", "bookkeeper"];

export function RecurringBillDetailPage() {
  const { id } = useParams<{ id: string }>();
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? WRITE_ROLES.includes(role) : false;

  const [template, setTemplate] =
    useState<RecurringBillTemplateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (!id) return;
    try {
      const res = await api.get(
        `/api/v1/recurring-bills/${id}` as "/api/v1/recurring-bills/{template_id}",
      );
      setTemplate(res.data as unknown as RecurringBillTemplateResponse);
    } catch {
      setError("Failed to load template.");
    }
  }, [id]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  async function action(path: string, label: string) {
    if (!id) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await apiClient.post(`/api/v1/recurring-bills/${id}/${path}`, null);
      setNotice(`${label} succeeded.`);
      await refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : `Could not ${label}.`);
    } finally {
      setBusy(false);
    }
  }

  if (!template) {
    return error ? (
      <p role="alert" className="text-sm text-destructive">
        {error}
      </p>
    ) : (
      <p className="text-sm text-muted-foreground">Loading…</p>
    );
  }

  const isActive = template.state === "active";
  const isPaused = template.state === "paused";
  const isCancelled = template.state === "cancelled";

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">{template.name}</h1>
          <p className="text-sm text-muted-foreground">
            State:{" "}
            <span data-testid="recurring-bill-state">{template.state}</span>{" "}
            · every {template.cadence_interval} {template.cadence_kind} · next
            issue {new Date(template.next_issue_at).toLocaleDateString()}
          </p>
        </div>
        <div className="flex gap-2">
          {canWrite && !isCancelled ? (
            <Button asChild variant="outline">
              <Link to={`/recurring-bills/${template.id}/edit`}>Edit</Link>
            </Button>
          ) : null}
          <Button variant="outline" asChild>
            <Link to="/recurring-bills">Back</Link>
          </Button>
        </div>
      </header>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p
          role="status"
          className="rounded border border-border bg-muted/30 p-3 text-sm"
          data-testid="recurring-bill-notice"
        >
          {notice}
        </p>
      ) : null}

      {canWrite ? (
        <div
          className="flex flex-wrap gap-2"
          data-testid="recurring-bill-actions"
        >
          {isActive ? (
            <Button
              disabled={busy}
              onClick={() => void action("pause", "Pause")}
              data-testid="action-pause"
            >
              Pause
            </Button>
          ) : null}
          {isPaused ? (
            <Button
              disabled={busy}
              onClick={() => void action("resume", "Resume")}
              data-testid="action-resume"
            >
              Resume
            </Button>
          ) : null}
          {isActive || isPaused ? (
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() => {
                if (!window.confirm("Cancel this template? Permanent.")) return;
                void action("cancel", "Cancel");
              }}
              data-testid="action-cancel"
            >
              Cancel
            </Button>
          ) : null}
          {isActive ? (
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => void action("materialize-now", "Materialize")}
              data-testid="action-materialize"
            >
              Materialize now
            </Button>
          ) : null}
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-lg border border-border p-4 text-sm">
          <h2 className="font-semibold">Header</h2>
          <dl className="mt-2 grid grid-cols-2 gap-y-1">
            <dt className="text-muted-foreground">Vendor</dt>
            <dd className="font-mono">{template.vendor_id.slice(0, 8)}</dd>
            <dt className="text-muted-foreground">Start</dt>
            <dd>{new Date(template.start_at).toLocaleDateString()}</dd>
            <dt className="text-muted-foreground">End</dt>
            <dd>
              {template.end_at
                ? new Date(template.end_at).toLocaleDateString()
                : "—"}
            </dd>
            <dt className="text-muted-foreground">Last issued</dt>
            <dd>
              {template.last_issued_at
                ? new Date(template.last_issued_at).toLocaleDateString()
                : "—"}
            </dd>
            <dt className="text-muted-foreground">Auto-issue</dt>
            <dd>{template.auto_issue ? "yes" : "no"}</dd>
          </dl>
        </div>
        <div className="rounded-lg border border-border p-4 text-sm">
          <h2 className="font-semibold">Totals</h2>
          <dl className="mt-2 grid grid-cols-2 gap-y-1">
            <dt className="text-muted-foreground">Discount</dt>
            <dd className="text-right font-mono">
              ${template.discount_amount}
            </dd>
            <dt className="text-muted-foreground">Tax</dt>
            <dd className="text-right font-mono">${template.tax_amount}</dd>
          </dl>
          {template.notes ? (
            <p className="mt-2 whitespace-pre-line text-xs text-muted-foreground">
              {template.notes}
            </p>
          ) : null}
        </div>
      </div>

      <div className="rounded-lg border border-border p-4">
        <h2 className="text-sm font-semibold">Lines</h2>
        <table className="mt-2 w-full table-fixed border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
              <th className="py-2 pr-2">#</th>
              <th className="py-2 pr-2">Kind</th>
              <th className="py-2 pr-2">Description</th>
              <th className="py-2 pr-2 text-right">Qty</th>
              <th className="py-2 pr-2 text-right">Unit</th>
            </tr>
          </thead>
          <tbody>
            {(template.items ?? []).map((it) => (
              <tr key={it.id} className="border-b border-border/50">
                <td className="py-2 pr-2 font-mono text-xs">{it.line_number}</td>
                <td className="py-2 pr-2">{it.kind}</td>
                <td className="py-2 pr-2">{it.description}</td>
                <td className="py-2 pr-2 text-right font-mono">
                  {it.quantity}
                </td>
                <td className="py-2 pr-2 text-right font-mono">
                  ${it.unit_price}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
