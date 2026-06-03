/**
 * `/quotes/:id` — read-only header + line table + state action bar
 * (Send / Accept / Decline / Expire / Cancel / Convert-to-invoice).
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type QuoteResponse = components["schemas"]["QuoteResponse"];

const WRITE_ROLES: readonly string[] = ["owner", "sales", "bookkeeper"];

interface Transition {
  label: string;
  path: string;
  variant?: "default" | "secondary" | "destructive" | "outline";
  allowed: ReadonlyArray<QuoteResponse["state"]>;
}

const TRANSITIONS: readonly Transition[] = [
  { label: "Send", path: "send", variant: "default", allowed: ["draft"] },
  { label: "Accept", path: "accept", variant: "secondary", allowed: ["sent"] },
  { label: "Decline", path: "decline", variant: "outline", allowed: ["sent"] },
  { label: "Expire", path: "expire", variant: "outline", allowed: ["sent"] },
  {
    label: "Cancel",
    path: "cancel",
    variant: "destructive",
    allowed: ["draft", "sent"],
  },
];

export function QuoteDetailPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? WRITE_ROLES.includes(role) : false;

  const [quote, setQuote] = useState<QuoteResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refetch = useCallback(async () => {
    if (!id) return;
    try {
      const res = await api.get(
        `/api/v1/quotes/${id}` as "/api/v1/quotes/{quote_id}",
      );
      setQuote(res.data as unknown as QuoteResponse);
    } catch {
      setError("Failed to load quote.");
    }
  }, [id]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  async function transition(path: string) {
    if (!id) return;
    setBusy(true);
    try {
      await apiClient.post(`/api/v1/quotes/${id}/${path}`, null);
      await refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : `Could not ${path} quote.`);
    } finally {
      setBusy(false);
    }
  }

  async function convert() {
    if (!id) return;
    if (!window.confirm("Convert this quote to an invoice?")) return;
    setBusy(true);
    try {
      const res = await apiClient.post<{ id: string }>(
        `/api/v1/quotes/${id}/convert-to-invoice`,
        null,
      );
      navigate(`/invoices/${res.data.id}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not convert quote.");
    } finally {
      setBusy(false);
    }
  }

  if (!quote) {
    return error ? (
      <p role="alert" className="text-sm text-destructive">
        {error}
      </p>
    ) : (
      <p className="text-sm text-muted-foreground">Loading…</p>
    );
  }

  const allowed = TRANSITIONS.filter((t) => t.allowed.includes(quote.state));

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Quote {quote.quote_number}</h1>
          <p className="text-sm text-muted-foreground">
            State: <span data-testid="quote-state">{quote.state}</span>
            {quote.valid_until ? (
              <> · valid until {new Date(quote.valid_until).toLocaleDateString()}</>
            ) : null}
          </p>
        </div>
        <div className="flex gap-2">
          {quote.state === "draft" && canWrite ? (
            <Button asChild variant="outline">
              <Link to={`/quotes/${quote.id}/edit`}>Edit</Link>
            </Button>
          ) : null}
          <Button variant="outline" asChild>
            <Link to="/quotes">Back</Link>
          </Button>
        </div>
      </header>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {canWrite ? (
        <div className="flex flex-wrap gap-2" data-testid="quote-actions">
          {allowed.map((t) => (
            <Button
              key={t.path}
              variant={t.variant ?? "default"}
              disabled={busy}
              onClick={() => void transition(t.path)}
              data-testid={`transition-${t.path}`}
            >
              {t.label}
            </Button>
          ))}
          {quote.state === "accepted" && !quote.accepted_invoice_id ? (
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => void convert()}
              data-testid="convert-to-invoice"
            >
              Convert to invoice
            </Button>
          ) : null}
          {quote.accepted_invoice_id ? (
            <Button asChild variant="outline">
              <Link to={`/invoices/${quote.accepted_invoice_id}`}>
                View invoice
              </Link>
            </Button>
          ) : null}
        </div>
      ) : null}

      <div className="rounded-lg border border-border p-4">
        <h2 className="text-sm font-semibold">Lines</h2>
        <div className="overflow-x-auto">
          <table className="mt-2 w-full min-w-[32rem] table-fixed border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                <th className="py-2 pr-2">#</th>
                <th className="py-2 pr-2">Kind</th>
                <th className="py-2 pr-2">Description</th>
                <th className="py-2 pr-2 text-right">Qty</th>
                <th className="py-2 pr-2 text-right">Unit</th>
                <th className="py-2 pr-2 text-right">Extended</th>
              </tr>
            </thead>
            <tbody>
              {(quote.items ?? []).map((it) => (
                <tr key={it.id} className="border-b border-border/50">
                  <td className="py-2 pr-2 font-mono text-xs">{it.line_number}</td>
                  <td className="py-2 pr-2">{it.kind}</td>
                  <td className="py-2 pr-2">{it.description}</td>
                  <td className="py-2 pr-2 text-right font-mono">{it.quantity}</td>
                  <td className="py-2 pr-2 text-right font-mono">${it.unit_price}</td>
                  <td className="py-2 pr-2 text-right font-mono">
                    ${it.extended_amount}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-lg border border-border p-4 text-sm">
        <h2 className="font-semibold">Totals</h2>
        <dl className="mt-2 grid grid-cols-2 gap-y-1">
          <dt className="text-muted-foreground">Subtotal</dt>
          <dd className="text-right font-mono">${quote.subtotal}</dd>
          <dt className="text-muted-foreground">Discount</dt>
          <dd className="text-right font-mono">−${quote.discount_amount}</dd>
          <dt className="text-muted-foreground">Tax</dt>
          <dd className="text-right font-mono">${quote.tax_amount}</dd>
          <dt className="font-semibold">Total</dt>
          <dd className="text-right font-mono font-semibold">${quote.total_amount}</dd>
        </dl>
      </div>
    </section>
  );
}
