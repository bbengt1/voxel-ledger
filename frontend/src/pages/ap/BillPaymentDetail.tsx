/**
 * `/bill-payments/:id` — read-only payment detail with applications
 * table and a state action bar (Unapply / Bounce / Cancel) gated by
 * state + role.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type BillPaymentResponse = components["schemas"]["BillPaymentResponse"];

const WRITE_ROLES: readonly string[] = ["owner", "bookkeeper"];

export function BillPaymentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? WRITE_ROLES.includes(role) : false;

  const [payment, setPayment] = useState<BillPaymentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (!id) return;
    try {
      const res = await api.get(
        `/api/v1/bill-payments/${id}` as "/api/v1/bill-payments/{bill_payment_id}",
      );
      setPayment(res.data as unknown as BillPaymentResponse);
    } catch {
      setError("Failed to load bill payment.");
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
      await apiClient.post(`/api/v1/bill-payments/${id}/${path}`, null);
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

  if (!payment) {
    return error ? (
      <p role="alert" className="text-sm text-destructive">
        {error}
      </p>
    ) : (
      <p className="text-sm text-muted-foreground">Loading…</p>
    );
  }

  const isPosted = payment.state === "posted";
  const isPending = payment.state === "pending";

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">{payment.payment_number}</h1>
          <p className="text-sm text-muted-foreground">
            State: <span data-testid="bill-payment-state">{payment.state}</span>
            {" · "}occurred{" "}
            {new Date(payment.occurred_at).toLocaleDateString()} · method{" "}
            {payment.method}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link to="/bill-payments">Back</Link>
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
          data-testid="bill-payment-notice"
        >
          {notice}
        </p>
      ) : null}

      {canWrite ? (
        <div className="flex flex-wrap gap-2" data-testid="bill-payment-actions">
          {isPosted ? (
            <Button
              disabled={busy}
              onClick={() => void action("unapply", "Unapply")}
              data-testid="action-unapply"
            >
              Unapply
            </Button>
          ) : null}
          {isPosted ? (
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() => {
                if (!window.confirm("Mark this payment as bounced?")) return;
                void action("bounce", "Bounce");
              }}
              data-testid="action-bounce"
            >
              Bounce
            </Button>
          ) : null}
          {isPending ? (
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() => {
                if (!window.confirm("Cancel this pending payment?")) return;
                void action("cancel", "Cancel");
              }}
              data-testid="action-cancel"
            >
              Cancel
            </Button>
          ) : null}
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-lg border border-border p-4 text-sm">
          <h2 className="font-semibold">Header</h2>
          <dl className="mt-2 grid grid-cols-2 gap-y-1">
            <dt className="text-muted-foreground">Amount</dt>
            <dd className="text-right font-mono">${payment.amount}</dd>
            <dt className="text-muted-foreground">Reference</dt>
            <dd className="text-right">{payment.reference_number ?? "—"}</dd>
            <dt className="text-muted-foreground">Vendor</dt>
            <dd className="text-right font-mono">
              {payment.vendor_id.slice(0, 8)}
            </dd>
          </dl>
          {payment.notes ? (
            <p className="mt-2 whitespace-pre-line text-xs text-muted-foreground">
              {payment.notes}
            </p>
          ) : null}
        </div>
        <div className="rounded-lg border border-border p-4 text-sm">
          <h2 className="font-semibold">Applications</h2>
          {(payment.applications ?? []).length === 0 ? (
            <p className="mt-1 text-xs text-muted-foreground">
              No applications.
            </p>
          ) : (
            <ul className="mt-2 space-y-1 text-xs">
              {(payment.applications ?? []).map((a) => (
                <li
                  key={a.id}
                  className="flex justify-between border-b border-border/50 py-1"
                  data-testid={`application-${a.id}`}
                >
                  <Link
                    to={`/bills/${a.bill_id}`}
                    className="font-mono hover:underline"
                  >
                    {a.bill_id.slice(0, 8)}
                  </Link>
                  <span className="font-mono">${a.amount_applied}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
