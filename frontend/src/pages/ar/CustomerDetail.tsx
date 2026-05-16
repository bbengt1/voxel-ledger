/**
 * `/customers/:id` — summary card + tabs for Quotes / Invoices / Payments /
 * Credit balance. The lists are read-only embeds; clicking a row deep-
 * links into the corresponding detail page.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { SendStatementModal } from "@/components/ar/SendStatementModal";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type CustomerResponse = components["schemas"]["CustomerResponse"];
type QuoteResponse = components["schemas"]["QuoteResponse"];
type InvoiceResponse = components["schemas"]["InvoiceResponse"];
type PaymentResponse = components["schemas"]["PaymentResponse"];
type CreditBalanceResponse = components["schemas"]["CustomerCreditBalanceResponse"];

const CAN_WRITE: readonly string[] = ["owner", "sales", "bookkeeper"];

type Tab = "quotes" | "invoices" | "payments" | "credit";

export function CustomerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [customer, setCustomer] = useState<CustomerResponse | null>(null);
  const [tab, setTab] = useState<Tab>("invoices");
  const [quotes, setQuotes] = useState<QuoteResponse[]>([]);
  const [invoices, setInvoices] = useState<InvoiceResponse[]>([]);
  const [payments, setPayments] = useState<PaymentResponse[]>([]);
  const [credit, setCredit] = useState<CreditBalanceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [statementOpen, setStatementOpen] = useState(false);
  const [statementSentNotice, setStatementSentNotice] = useState<string | null>(
    null,
  );

  const refetchCustomer = useCallback(async () => {
    if (!id) return;
    try {
      const res = await api.get(
        `/api/v1/customers/${id}` as "/api/v1/customers/{customer_id}",
      );
      setCustomer(res.data as unknown as CustomerResponse);
    } catch {
      setError("Failed to load customer.");
    }
  }, [id]);

  useEffect(() => {
    void refetchCustomer();
  }, [refetchCustomer]);

  useEffect(() => {
    if (!id) return;
    api
      .get("/api/v1/quotes", { params: { customer_id: id } })
      .then((res) => setQuotes(res.data.items))
      .catch(() => setQuotes([]));
    api
      .get("/api/v1/invoices", { params: { customer_id: id } })
      .then((res) => setInvoices(res.data.items))
      .catch(() => setInvoices([]));
    api
      .get("/api/v1/payments", { params: { customer_id: id } })
      .then((res) => setPayments(res.data.items))
      .catch(() => setPayments([]));
    api
      .get(
        `/api/v1/customers/${id}/credit-balance` as "/api/v1/customers/{customer_id}/credit-balance",
      )
      .then((res) => setCredit(res.data as unknown as CreditBalanceResponse))
      .catch(() => setCredit(null));
  }, [id]);

  async function toggleArchive() {
    if (!customer) return;
    setBusy(true);
    try {
      const path =
        customer.state === "active"
          ? `/api/v1/customers/${customer.id}/archive`
          : `/api/v1/customers/${customer.id}/unarchive`;
      await apiClient.post(path);
      await refetchCustomer();
    } catch {
      setError("Could not change archive state.");
    } finally {
      setBusy(false);
    }
  }

  if (!customer) {
    return error ? (
      <p role="alert" className="text-sm text-destructive">
        {error}
      </p>
    ) : (
      <p className="text-sm text-muted-foreground">Loading…</p>
    );
  }

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">{customer.display_name}</h1>
          <p className="text-sm text-muted-foreground">
            {customer.customer_number} · {customer.state} ·{" "}
            {customer.payment_terms_days}-day terms
          </p>
        </div>
        <div className="flex gap-2">
          {canWrite ? (
            <>
              <Button asChild variant="outline">
                <Link to={`/customers/${customer.id}/edit`}>Edit</Link>
              </Button>
              <Button
                variant="outline"
                onClick={() => setStatementOpen(true)}
                data-testid="send-statement-btn"
              >
                Send statement
              </Button>
              <Button
                variant="outline"
                onClick={() => void toggleArchive()}
                disabled={busy}
                data-testid="toggle-archive"
              >
                {customer.state === "active" ? "Archive" : "Unarchive"}
              </Button>
            </>
          ) : null}
          <Button variant="outline" asChild>
            <Link to="/customers">Back</Link>
          </Button>
        </div>
      </header>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      {statementSentNotice ? (
        <p
          role="status"
          className="rounded border border-border bg-muted/30 p-3 text-sm"
          data-testid="statement-sent-notice"
        >
          {statementSentNotice}
        </p>
      ) : null}

      <div className="rounded-lg border border-border p-4 text-sm">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-xs uppercase text-muted-foreground">
              Primary email
            </div>
            <div>{customer.primary_email ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs uppercase text-muted-foreground">Phone</div>
            <div>{customer.phone ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs uppercase text-muted-foreground">
              Legal name
            </div>
            <div>{customer.legal_name ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs uppercase text-muted-foreground">
              Credit balance
            </div>
            <div className="font-mono" data-testid="credit-balance">
              ${credit?.available_amount ?? "0.00"}
            </div>
          </div>
        </div>
      </div>

      <div className="flex gap-2 border-b border-border">
        {(["invoices", "quotes", "payments", "credit"] as const).map((t) => (
          <button
            key={t}
            type="button"
            className={
              "px-3 py-2 text-sm " +
              (tab === t
                ? "border-b-2 border-foreground font-semibold"
                : "text-muted-foreground")
            }
            onClick={() => setTab(t)}
            data-testid={`tab-${t}`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "quotes" ? (
        <ul className="space-y-1 text-sm" data-testid="tab-content-quotes">
          {quotes.length === 0 ? (
            <li className="text-muted-foreground">No quotes.</li>
          ) : (
            quotes.map((q) => (
              <li
                key={q.id}
                className="flex justify-between border-b border-border/50 py-1"
              >
                <Link to={`/quotes/${q.id}`} className="font-mono hover:underline">
                  {q.quote_number}
                </Link>
                <span>{q.state}</span>
                <span className="font-mono">${q.total_amount}</span>
              </li>
            ))
          )}
        </ul>
      ) : null}

      {tab === "invoices" ? (
        <ul className="space-y-1 text-sm" data-testid="tab-content-invoices">
          {invoices.length === 0 ? (
            <li className="text-muted-foreground">No invoices.</li>
          ) : (
            invoices.map((i) => (
              <li
                key={i.id}
                className="flex justify-between border-b border-border/50 py-1"
              >
                <Link to={`/invoices/${i.id}`} className="font-mono hover:underline">
                  {i.invoice_number}
                </Link>
                <span>{i.state}</span>
                <span className="font-mono">${i.total_amount}</span>
              </li>
            ))
          )}
        </ul>
      ) : null}

      {tab === "payments" ? (
        <ul className="space-y-1 text-sm" data-testid="tab-content-payments">
          {payments.length === 0 ? (
            <li className="text-muted-foreground">No payments.</li>
          ) : (
            payments.map((p) => (
              <li
                key={p.id}
                className="flex justify-between border-b border-border/50 py-1"
              >
                <Link to={`/payments/${p.id}`} className="font-mono hover:underline">
                  {p.payment_number}
                </Link>
                <span>{p.state}</span>
                <span className="font-mono">${p.amount}</span>
              </li>
            ))
          )}
        </ul>
      ) : null}

      <SendStatementModal
        open={statementOpen}
        onOpenChange={setStatementOpen}
        customerId={customer.id}
        onSent={() => setStatementSentNotice("Statement queued for delivery.")}
      />

      {tab === "credit" ? (
        <div className="rounded-lg border border-border p-4 text-sm" data-testid="tab-content-credit">
          <p>
            Available credit:{" "}
            <span className="font-mono font-semibold">
              ${credit?.available_amount ?? "0.00"}
            </span>
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Credit is applied at payment time when excess is collected on
            invoices.
          </p>
        </div>
      ) : null}
    </section>
  );
}
