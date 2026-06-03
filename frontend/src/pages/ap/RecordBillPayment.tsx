/**
 * `/bill-payments/new` — record a payment against one or more open bills
 * for a vendor. Mirrors RecordPayment (AR) but posts a single body with
 * an `applications` array per the BillPaymentCreate schema.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { VendorPicker, type VendorOption } from "@/components/ap/VendorPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type BillResponse = components["schemas"]["BillResponse"];
type BillPaymentCreate = components["schemas"]["BillPaymentCreate"];
type BillPaymentResponse = components["schemas"]["BillPaymentResponse"];
type BillPaymentApplicationInput =
  components["schemas"]["BillPaymentApplicationInput"];
type PaymentMethod = BillPaymentCreate["method"];

const METHODS: PaymentMethod[] = [
  "cash",
  "check",
  "ach",
  "wire",
  "card",
  "other",
];

const OPEN_STATES = ["issued", "partially_paid", "overdue"] as const;

function num(v: string): number {
  const n = Number.parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

export function RecordBillPaymentPage() {
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const initialBillId = search.get("bill_id") ?? "";

  const [vendor, setVendor] = useState<VendorOption | null>(null);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<PaymentMethod>("ach");
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");
  const [occurredAt, setOccurredAt] = useState(
    () => new Date().toISOString().slice(0, 10),
  );
  const [openBills, setOpenBills] = useState<BillResponse[]>([]);
  const [allocations, setAllocations] = useState<Record<string, string>>({});

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!vendor) {
      setOpenBills([]);
      return;
    }
    let cancelled = false;
    Promise.all(
      OPEN_STATES.map((s) =>
        api.get("/api/v1/bills", {
          params: { vendor_id: vendor.id, state: s },
        }),
      ),
    )
      .then((results) => {
        if (cancelled) return;
        const all: BillResponse[] = [];
        for (const r of results) {
          for (const it of r.data.items) all.push(it);
        }
        setOpenBills(all);
        if (initialBillId) {
          const match = all.find((i) => i.id === initialBillId);
          if (match) {
            setAllocations({ [match.id]: match.amount_outstanding });
            if (!amount) setAmount(match.amount_outstanding);
          }
        }
      })
      .catch(() => {
        if (!cancelled) setOpenBills([]);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vendor]);

  const allocated = useMemo(
    () => Object.values(allocations).reduce((acc, v) => acc + num(v), 0),
    [allocations],
  );

  const totalAmount = num(amount);
  const remaining = totalAmount - allocated;

  async function submit() {
    if (!vendor) {
      setError("Pick a vendor.");
      return;
    }
    if (totalAmount <= 0) {
      setError("Amount must be greater than 0.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const applications: BillPaymentApplicationInput[] = [];
      for (const [billId, amtStr] of Object.entries(allocations)) {
        const n = num(amtStr);
        if (n > 0) applications.push({ bill_id: billId, amount_applied: amtStr });
      }
      const body: BillPaymentCreate = {
        vendor_id: vendor.id,
        amount,
        method,
        occurred_at: new Date(occurredAt).toISOString(),
        applications,
      };
      if (reference.trim()) body.reference_number = reference.trim();
      if (notes.trim()) body.notes = notes.trim();
      const res = await apiClient.post<BillPaymentResponse>(
        "/api/v1/bill-payments",
        body,
      );
      navigate(`/bill-payments/${res.data.id}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : "Could not record payment.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Record bill payment</h1>
      </header>

      <div className="space-y-3 rounded-lg border border-border p-4">
        <h2 className="text-sm font-semibold">Header</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="block text-sm">
            Vendor
            <VendorPicker
              value={vendor}
              onChange={setVendor}
              data-testid="bill-payment-vendor-picker"
            />
          </label>
          <label className="block text-sm">
            Occurred at
            <Input
              type="date"
              value={occurredAt}
              onChange={(e) => setOccurredAt(e.target.value)}
              data-testid="bill-payment-occurred-at"
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
              data-testid="bill-payment-amount"
            />
          </label>
          <label className="block text-sm">
            Method
            <select
              className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              value={method}
              onChange={(e) => setMethod(e.target.value as PaymentMethod)}
              data-testid="bill-payment-method"
            >
              {METHODS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            Reference number
            <Input
              value={reference}
              onChange={(e) => setReference(e.target.value)}
              data-testid="bill-payment-reference"
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
            data-testid="bill-payment-notes"
          />
        </label>
      </div>

      <div className="space-y-3 rounded-lg border border-border p-4">
        <h2 className="text-sm font-semibold">Allocations</h2>
        {!vendor ? (
          <p className="text-xs text-muted-foreground">
            Pick a vendor to see open bills.
          </p>
        ) : openBills.length === 0 ? (
          <p
            className="text-xs text-muted-foreground"
            data-testid="no-open-bills"
          >
            No open bills for this vendor.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[32rem] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                  <th className="py-1 pr-2">Bill</th>
                  <th className="py-1 pr-2">Due</th>
                  <th className="py-1 pr-2 text-right">Outstanding</th>
                  <th className="py-1 pr-2 text-right">Apply</th>
                </tr>
              </thead>
              <tbody>
                {openBills.map((b) => (
                  <tr
                    key={b.id}
                    className="border-b border-border/50"
                    data-testid={`alloc-row-${b.id}`}
                  >
                    <td className="py-1 pr-2 font-mono text-xs">
                      {b.bill_number}
                    </td>
                    <td className="py-1 pr-2 text-xs">
                      {b.due_at
                        ? new Date(b.due_at).toLocaleDateString()
                        : "—"}
                    </td>
                    <td className="py-1 pr-2 text-right font-mono">
                      ${b.amount_outstanding}
                    </td>
                    <td className="py-1 pr-2 text-right">
                      <Input
                        type="number"
                        step="0.01"
                        min={0}
                        value={allocations[b.id] ?? ""}
                        onChange={(e) =>
                          setAllocations((prev) => ({
                            ...prev,
                            [b.id]: e.target.value,
                          }))
                        }
                        data-testid={`alloc-input-${b.id}`}
                        className="w-28 text-right"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div
          className="flex items-center justify-end text-xs"
          data-testid="allocation-summary"
        >
          Allocated: ${allocated.toFixed(2)} · Remaining: $
          {remaining.toFixed(2)}
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
          data-testid="record-bill-payment-submit"
        >
          {submitting ? "Recording…" : "Record payment"}
        </Button>
        <Button
          variant="outline"
          disabled={submitting}
          onClick={() => navigate("/bill-payments")}
        >
          Cancel
        </Button>
      </div>
    </section>
  );
}
