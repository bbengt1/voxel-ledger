/**
 * `/payments/new` — record a payment for a customer.
 *
 * Picking a customer loads their open invoices (issued / partially-paid /
 * overdue). The operator allocates the payment amount across one or more
 * invoices; any excess can be parked on the customer's credit balance via
 * the "apply excess to credit" checkbox.
 *
 * Flow: POST /payments (creates pending payment) → POST /payments/:id/apply
 * with the allocation array.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import {
  CustomerPicker,
  type CustomerOption,
} from "@/components/ar/CustomerPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type InvoiceResponse = components["schemas"]["InvoiceResponse"];
type PaymentCreate = components["schemas"]["PaymentCreate"];
type PaymentResponse = components["schemas"]["PaymentResponse"];
type PaymentApplicationInput = components["schemas"]["PaymentApplicationInput"];
type PaymentMethod = PaymentCreate["method"];

const METHODS: PaymentMethod[] = [
  "cash",
  "check",
  "ach",
  "wire",
  "card",
  "marketplace",
  "other",
];

const OPEN_STATES = ["issued", "partially_paid", "overdue"] as const;

function num(v: string): number {
  const n = Number.parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

export function RecordPaymentPage() {
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const initialInvoiceId = search.get("invoice_id") ?? "";

  const [customer, setCustomer] = useState<CustomerOption | null>(null);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<PaymentMethod>("ach");
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");
  const [receivedAt, setReceivedAt] = useState(
    () => new Date().toISOString().slice(0, 10),
  );
  const [openInvoices, setOpenInvoices] = useState<InvoiceResponse[]>([]);
  const [allocations, setAllocations] = useState<Record<string, string>>({});
  const [applyExcessToCredit, setApplyExcessToCredit] = useState(true);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!customer) {
      setOpenInvoices([]);
      return;
    }
    let cancelled = false;
    Promise.all(
      OPEN_STATES.map((s) =>
        api.get("/api/v1/invoices", {
          params: { customer_id: customer.id, state: s },
        }),
      ),
    )
      .then((results) => {
        if (cancelled) return;
        const all: InvoiceResponse[] = [];
        for (const r of results) {
          for (const it of r.data.items) all.push(it);
        }
        setOpenInvoices(all);
        if (initialInvoiceId) {
          const match = all.find((i) => i.id === initialInvoiceId);
          if (match) {
            setAllocations({ [match.id]: match.amount_outstanding });
            if (!amount) setAmount(match.amount_outstanding);
          }
        }
      })
      .catch(() => {
        if (!cancelled) setOpenInvoices([]);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customer]);

  const allocated = useMemo(
    () =>
      Object.values(allocations).reduce((acc, v) => acc + num(v), 0),
    [allocations],
  );

  const totalAmount = num(amount);
  const remaining = totalAmount - allocated;

  async function submit() {
    if (!customer) {
      setError("Pick a customer.");
      return;
    }
    if (totalAmount <= 0) {
      setError("Amount must be greater than 0.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const body: PaymentCreate = {
        customer_id: customer.id,
        amount,
        method,
        received_at: new Date(receivedAt).toISOString(),
        deposit_to_undeposited: false,
      };
      if (reference.trim()) body.reference = reference.trim();
      if (notes.trim()) body.notes = notes.trim();
      const res = await apiClient.post<PaymentResponse>(
        "/api/v1/payments",
        body,
      );
      const paymentId = res.data.id;

      const applications: PaymentApplicationInput[] = [];
      for (const [invoiceId, amtStr] of Object.entries(allocations)) {
        const n = num(amtStr);
        if (n > 0) applications.push({ invoice_id: invoiceId, amount: amtStr });
      }
      if (applications.length > 0 || applyExcessToCredit) {
        await apiClient.post(`/api/v1/payments/${paymentId}/apply`, {
          applications,
          apply_excess_to_credit: applyExcessToCredit,
        });
      }
      navigate(`/payments/${paymentId}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not record payment.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Record payment</h1>
      </header>

      <div className="space-y-3 rounded-lg border border-border p-4">
        <h2 className="text-sm font-semibold">Header</h2>
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm">
            Customer
            <CustomerPicker
              value={customer}
              onChange={setCustomer}
              data-testid="payment-customer-picker"
            />
          </label>
          <label className="block text-sm">
            Received at
            <Input
              type="date"
              value={receivedAt}
              onChange={(e) => setReceivedAt(e.target.value)}
              data-testid="payment-received-at"
            />
          </label>
          <label className="block text-sm">
            Amount
            <Input
              type="number"
              step="0.01"
              min={0}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              data-testid="payment-amount"
            />
          </label>
          <label className="block text-sm">
            Method
            <select
              className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              value={method}
              onChange={(e) => setMethod(e.target.value as PaymentMethod)}
              data-testid="payment-method"
            >
              {METHODS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            Reference
            <Input
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              data-testid="payment-reference"
            />
          </label>
        </div>
        <label className="block text-sm">
          Notes
          <textarea
            className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            data-testid="payment-notes"
          />
        </label>
      </div>

      <div className="space-y-3 rounded-lg border border-border p-4">
        <h2 className="text-sm font-semibold">Allocations</h2>
        {!customer ? (
          <p className="text-xs text-muted-foreground">
            Pick a customer to see open invoices.
          </p>
        ) : openInvoices.length === 0 ? (
          <p
            className="text-xs text-muted-foreground"
            data-testid="no-open-invoices"
          >
            No open invoices for this customer.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                <th className="py-1 pr-2">Invoice</th>
                <th className="py-1 pr-2">Due</th>
                <th className="py-1 pr-2 text-right">Outstanding</th>
                <th className="py-1 pr-2 text-right">Apply</th>
              </tr>
            </thead>
            <tbody>
              {openInvoices.map((inv) => (
                <tr
                  key={inv.id}
                  className="border-b border-border/50"
                  data-testid={`alloc-row-${inv.id}`}
                >
                  <td className="py-1 pr-2 font-mono text-xs">
                    {inv.invoice_number}
                  </td>
                  <td className="py-1 pr-2 text-xs">
                    {inv.due_at
                      ? new Date(inv.due_at).toLocaleDateString()
                      : "—"}
                  </td>
                  <td className="py-1 pr-2 text-right font-mono">
                    ${inv.amount_outstanding}
                  </td>
                  <td className="py-1 pr-2 text-right">
                    <Input
                      type="number"
                      step="0.01"
                      min={0}
                      value={allocations[inv.id] ?? ""}
                      onChange={(e) =>
                        setAllocations((prev) => ({
                          ...prev,
                          [inv.id]: e.target.value,
                        }))
                      }
                      data-testid={`alloc-input-${inv.id}`}
                      className="w-28 text-right"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="flex items-center justify-between text-xs">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={applyExcessToCredit}
              onChange={(e) => setApplyExcessToCredit(e.target.checked)}
              data-testid="excess-to-credit"
            />
            Apply excess to customer credit
          </label>
          <div data-testid="allocation-summary">
            Allocated: ${allocated.toFixed(2)} · Remaining: $
            {remaining.toFixed(2)}
          </div>
        </div>
      </div>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="flex gap-2">
        <Button
          disabled={submitting}
          onClick={() => void submit()}
          data-testid="record-payment-submit"
        >
          {submitting ? "Recording…" : "Record payment"}
        </Button>
        <Button
          variant="outline"
          disabled={submitting}
          onClick={() => navigate("/payments")}
        >
          Cancel
        </Button>
      </div>
    </section>
  );
}
