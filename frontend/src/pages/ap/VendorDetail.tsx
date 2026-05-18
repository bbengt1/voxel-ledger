/**
 * `/vendors/:id` — summary card + tabs for Bills / Bill payments /
 * Recurring bills / Expense claims. Tabs are filtered lists keyed by
 * vendor_id.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type VendorResponse = components["schemas"]["VendorResponse"];
type BillResponse = components["schemas"]["BillResponse"];
type BillPaymentResponse = components["schemas"]["BillPaymentResponse"];
type RecurringBillResponse =
  components["schemas"]["RecurringBillTemplateResponse"];
type ExpenseClaimResponse = components["schemas"]["ExpenseClaimResponse"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

type Tab = "bills" | "payments" | "recurring" | "claims";

export function VendorDetailPage() {
  const { id } = useParams<{ id: string }>();
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [vendor, setVendor] = useState<VendorResponse | null>(null);
  const [tab, setTab] = useState<Tab>("bills");
  const [bills, setBills] = useState<BillResponse[]>([]);
  const [payments, setPayments] = useState<BillPaymentResponse[]>([]);
  const [recurring, setRecurring] = useState<RecurringBillResponse[]>([]);
  const [claims, setClaims] = useState<ExpenseClaimResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refetchVendor = useCallback(async () => {
    if (!id) return;
    try {
      const res = await api.get(
        `/api/v1/vendors/${id}` as "/api/v1/vendors/{vendor_id}",
      );
      setVendor(res.data as unknown as VendorResponse);
    } catch {
      setError("Failed to load vendor.");
    }
  }, [id]);

  useEffect(() => {
    void refetchVendor();
  }, [refetchVendor]);

  useEffect(() => {
    if (!id) return;
    api
      .get("/api/v1/bills", { params: { vendor_id: id } })
      .then((res) => setBills(res.data.items))
      .catch(() => setBills([]));
    api
      .get("/api/v1/bill-payments", { params: { vendor_id: id } })
      .then((res) => setPayments(res.data.items))
      .catch(() => setPayments([]));
    api
      .get("/api/v1/recurring-bills", { params: { vendor_id: id } })
      .then((res) => setRecurring(res.data.items))
      .catch(() => setRecurring([]));
    // Expense claims are not vendor-scoped; we only show the unbilled
    // pull-flow source on the invoice side. Leave empty here.
    setClaims([]);
  }, [id]);

  async function toggleArchive() {
    if (!vendor) return;
    setBusy(true);
    try {
      const path =
        vendor.state === "active"
          ? `/api/v1/vendors/${vendor.id}/archive`
          : `/api/v1/vendors/${vendor.id}/unarchive`;
      await apiClient.post(path);
      await refetchVendor();
    } catch {
      setError("Could not change archive state.");
    } finally {
      setBusy(false);
    }
  }

  if (!vendor) {
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
          <h1 className="text-xl font-semibold">{vendor.display_name}</h1>
          <p className="text-sm text-muted-foreground">
            {vendor.vendor_number} · {vendor.state} ·{" "}
            {vendor.payment_terms_days}-day terms
            {vendor.is_1099_vendor ? " · 1099" : ""}
          </p>
        </div>
        <div className="flex gap-2">
          {canWrite ? (
            <>
              <Button asChild variant="outline">
                <Link to={`/vendors/${vendor.id}/edit`}>Edit</Link>
              </Button>
              <Button
                variant="outline"
                onClick={() => void toggleArchive()}
                disabled={busy}
                data-testid="toggle-archive"
              >
                {vendor.state === "active" ? "Archive" : "Unarchive"}
              </Button>
            </>
          ) : null}
          <Button variant="outline" asChild>
            <Link to="/vendors">Back</Link>
          </Button>
        </div>
      </header>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="rounded-lg border border-border p-4 text-sm">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-xs uppercase text-muted-foreground">
              Primary email
            </div>
            <div>{vendor.primary_email ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs uppercase text-muted-foreground">Phone</div>
            <div>{vendor.phone ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs uppercase text-muted-foreground">
              Legal name
            </div>
            <div>{vendor.legal_name ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs uppercase text-muted-foreground">Tax ID</div>
            <div>{vendor.tax_id ?? "—"}</div>
          </div>
        </div>
      </div>

      <div className="flex gap-2 border-b border-border">
        {(["bills", "payments", "recurring", "claims"] as const).map((t) => (
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

      {tab === "bills" ? (
        <ul className="space-y-1 text-sm" data-testid="tab-content-bills">
          {bills.length === 0 ? (
            <li className="text-muted-foreground">No bills.</li>
          ) : (
            bills.map((b) => (
              <li
                key={b.id}
                className="flex justify-between border-b border-border/50 py-1"
              >
                <Link to={`/bills/${b.id}`} className="font-mono hover:underline">
                  {b.bill_number}
                </Link>
                <span>{b.state}</span>
                <span className="font-mono">${b.total_amount}</span>
              </li>
            ))
          )}
        </ul>
      ) : null}

      {tab === "payments" ? (
        <ul className="space-y-1 text-sm" data-testid="tab-content-payments">
          {payments.length === 0 ? (
            <li className="text-muted-foreground">No bill payments.</li>
          ) : (
            payments.map((p) => (
              <li
                key={p.id}
                className="flex justify-between border-b border-border/50 py-1"
              >
                <Link
                  to={`/bill-payments/${p.id}`}
                  className="font-mono hover:underline"
                >
                  {p.payment_number}
                </Link>
                <span>{p.state}</span>
                <span className="font-mono">${p.amount}</span>
              </li>
            ))
          )}
        </ul>
      ) : null}

      {tab === "recurring" ? (
        <ul className="space-y-1 text-sm" data-testid="tab-content-recurring">
          {recurring.length === 0 ? (
            <li className="text-muted-foreground">No recurring bills.</li>
          ) : (
            recurring.map((t) => (
              <li
                key={t.id}
                className="flex justify-between border-b border-border/50 py-1"
              >
                <Link
                  to={`/recurring-bills/${t.id}`}
                  className="font-mono hover:underline"
                >
                  {t.name}
                </Link>
                <span>{t.state}</span>
                <span>
                  every {t.cadence_interval} {t.cadence_kind}
                </span>
              </li>
            ))
          )}
        </ul>
      ) : null}

      {tab === "claims" ? (
        <ul className="space-y-1 text-sm" data-testid="tab-content-claims">
          {claims.length === 0 ? (
            <li className="text-muted-foreground">
              Claims are submitter-scoped — see the Expense claims page.
            </li>
          ) : (
            claims.map((c) => (
              <li
                key={c.id}
                className="flex justify-between border-b border-border/50 py-1"
              >
                <Link
                  to={`/expense-claims/${c.id}`}
                  className="font-mono hover:underline"
                >
                  {c.claim_number}
                </Link>
                <span>{c.state}</span>
                <span className="font-mono">${c.total_amount}</span>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </section>
  );
}
