/**
 * `/payments/:id` — payment detail with applications table + Unapply /
 * Mark-bounced / Cancel actions gated by state + role.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type PaymentResponse = components["schemas"]["PaymentResponse"];

const WRITE_ROLES: readonly string[] = ["owner", "bookkeeper"];

export function PaymentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? WRITE_ROLES.includes(role) : false;

  const [payment, setPayment] = useState<PaymentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refetch = useCallback(async () => {
    if (!id) return;
    try {
      const res = await api.get(
        `/api/v1/payments/${id}` as "/api/v1/payments/{payment_id}",
      );
      setPayment(res.data as unknown as PaymentResponse);
    } catch {
      setError("Failed to load payment.");
    }
  }, [id]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  async function action(path: string, confirmMsg?: string) {
    if (!id) return;
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    setBusy(true);
    try {
      await apiClient.post(`/api/v1/payments/${id}/${path}`, null);
      await refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : `Could not ${path}.`);
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

  const canUnapply =
    payment.state === "applied" && (payment.applications?.length ?? 0) > 0;
  const canBounce =
    payment.state === "pending" || payment.state === "applied";
  const canCancel = payment.state === "pending";

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">
            Payment {payment.payment_number}
          </h1>
          <p className="text-sm text-muted-foreground">
            State: <span data-testid="payment-state">{payment.state}</span> ·{" "}
            {payment.method} · ${payment.amount}
          </p>
        </div>
        <Button variant="outline" asChild>
          <Link to="/payments">Back</Link>
        </Button>
      </header>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {canWrite ? (
        <div className="flex flex-wrap gap-2" data-testid="payment-actions">
          {canUnapply ? (
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => void action("unapply", "Unapply this payment?")}
              data-testid="action-unapply"
            >
              Unapply
            </Button>
          ) : null}
          {canBounce ? (
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() => void action("mark-bounced", "Mark payment bounced?")}
              data-testid="action-bounced"
            >
              Mark bounced
            </Button>
          ) : null}
          {canCancel ? (
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() => void action("cancel", "Cancel this payment?")}
              data-testid="action-cancel"
            >
              Cancel
            </Button>
          ) : null}
        </div>
      ) : null}

      <div className="rounded-lg border border-border p-4 text-sm">
        <h2 className="font-semibold">Applications</h2>
        {(payment.applications ?? []).length === 0 ? (
          <p className="mt-1 text-xs text-muted-foreground">
            This payment has no applications.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="mt-2 w-full min-w-[28rem] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                  <th className="py-1 pr-2">Invoice</th>
                  <th className="py-1 pr-2">Applied at</th>
                  <th className="py-1 pr-2 text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {(payment.applications ?? []).map((a) => (
                  <tr
                    key={a.id}
                    className="border-b border-border/50"
                    data-testid={`application-${a.id}`}
                  >
                    <td className="py-1 pr-2 font-mono text-xs">
                      <Link
                        to={`/invoices/${a.invoice_id}`}
                        className="hover:underline"
                      >
                        {a.invoice_id.slice(0, 8)}
                      </Link>
                    </td>
                    <td className="py-1 pr-2 text-xs">
                      {new Date(a.applied_at).toLocaleString()}
                    </td>
                    <td className="py-1 pr-2 text-right font-mono">${a.amount}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
