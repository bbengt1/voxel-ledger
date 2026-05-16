/**
 * `/late-fee-policies/new` and `/late-fee-policies/:id` — create or edit a
 * late-fee policy. Operator picks global vs customer-specific, kind,
 * amount, grace + apply-after windows, and (for compound) interval days.
 * The detail page (this same component when editing) exposes a
 * "Deactivate" action.
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import {
  CustomerPicker,
  type CustomerOption,
} from "@/components/ar/CustomerPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type LateFeePolicyResponse = components["schemas"]["LateFeePolicyResponse"];
type LateFeePolicyCreate = components["schemas"]["LateFeePolicyCreate"];
type LateFeePolicyUpdate = components["schemas"]["LateFeePolicyUpdate"];

type Kind = "percent_of_outstanding" | "flat" | "compound_percent";

const KINDS: readonly Kind[] = [
  "percent_of_outstanding",
  "flat",
  "compound_percent",
];

export function LateFeePolicyComposerPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);

  const [scope, setScope] = useState<"global" | "customer">("global");
  const [customer, setCustomer] = useState<CustomerOption | null>(null);
  const [kind, setKind] = useState<Kind>("percent_of_outstanding");
  const [amount, setAmount] = useState("0");
  const [graceDays, setGraceDays] = useState("0");
  const [applyAfterDays, setApplyAfterDays] = useState("30");
  const [compoundIntervalDays, setCompoundIntervalDays] = useState("30");
  const [notes, setNotes] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (!id) return;
    try {
      const res = await api.get(
        `/api/v1/late-fee-policies/${id}` as "/api/v1/late-fee-policies/{policy_id}",
      );
      const p = res.data as unknown as LateFeePolicyResponse;
      setScope(p.customer_id ? "customer" : "global");
      if (p.customer_id) {
        setCustomer({ id: p.customer_id, label: p.customer_id.slice(0, 8) });
      }
      setKind(p.kind);
      setAmount(p.amount);
      setGraceDays(String(p.grace_period_days));
      setApplyAfterDays(String(p.apply_after_days));
      setCompoundIntervalDays(String(p.compound_interval_days));
      setNotes(p.notes ?? "");
      setIsActive(p.is_active);
    } catch {
      setError("Could not load policy.");
    }
  }, [id]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  async function submit() {
    if (scope === "customer" && !customer) {
      setError("Pick a customer or switch to global.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      if (isEdit && id) {
        const body: LateFeePolicyUpdate = {
          kind,
          amount,
          grace_period_days: Number.parseInt(graceDays, 10) || 0,
          apply_after_days: Number.parseInt(applyAfterDays, 10) || 0,
          compound_interval_days:
            Number.parseInt(compoundIntervalDays, 10) || 0,
          notes: notes.trim() || null,
        };
        await apiClient.patch(`/api/v1/late-fee-policies/${id}`, body);
        navigate(`/late-fee-policies/${id}`);
        await refetch();
      } else {
        const body: LateFeePolicyCreate = {
          customer_id: scope === "customer" && customer ? customer.id : null,
          kind,
          amount,
          grace_period_days: Number.parseInt(graceDays, 10) || 0,
          apply_after_days: Number.parseInt(applyAfterDays, 10) || 30,
          compound_interval_days:
            Number.parseInt(compoundIntervalDays, 10) || 30,
          is_active: true,
        };
        if (notes.trim()) body.notes = notes.trim();
        const res = await apiClient.post<LateFeePolicyResponse>(
          "/api/v1/late-fee-policies",
          body,
        );
        navigate(`/late-fee-policies/${res.data.id}`);
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not save policy.");
    } finally {
      setSubmitting(false);
    }
  }

  async function deactivate() {
    if (!id) return;
    if (!window.confirm("Deactivate this policy?")) return;
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      await apiClient.post(
        `/api/v1/late-fee-policies/${id}/deactivate`,
        null,
      );
      setNotice("Policy deactivated.");
      await refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : "Could not deactivate.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="max-w-2xl space-y-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">
          {isEdit ? "Late-fee policy" : "New late-fee policy"}
        </h1>
        {isEdit && isActive ? (
          <Button
            variant="destructive"
            disabled={busy}
            onClick={() => void deactivate()}
            data-testid="action-deactivate"
          >
            Deactivate
          </Button>
        ) : null}
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
          data-testid="policy-notice"
        >
          {notice}
        </p>
      ) : null}

      <div className="space-y-3 rounded-lg border border-border p-4">
        <fieldset className="space-y-2 text-sm">
          <legend className="font-semibold">Scope</legend>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="scope"
              value="global"
              checked={scope === "global"}
              onChange={() => setScope("global")}
              disabled={isEdit}
              data-testid="scope-global"
            />
            Global (applies to all customers)
          </label>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="scope"
              value="customer"
              checked={scope === "customer"}
              onChange={() => setScope("customer")}
              disabled={isEdit}
              data-testid="scope-customer"
            />
            Specific customer
          </label>
          {scope === "customer" ? (
            <CustomerPicker
              value={customer}
              onChange={setCustomer}
              disabled={isEdit}
              data-testid="policy-customer-picker"
            />
          ) : null}
        </fieldset>
      </div>

      <div className="space-y-3 rounded-lg border border-border p-4">
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm">
            Kind
            <select
              className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              value={kind}
              onChange={(e) => setKind(e.target.value as Kind)}
              data-testid="policy-kind"
            >
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            Amount
            <Input
              type="number"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              data-testid="policy-amount"
            />
          </label>
          <label className="block text-sm">
            Grace period (days)
            <Input
              type="number"
              min={0}
              value={graceDays}
              onChange={(e) => setGraceDays(e.target.value)}
              data-testid="policy-grace-days"
            />
          </label>
          <label className="block text-sm">
            Apply after (days)
            <Input
              type="number"
              min={0}
              value={applyAfterDays}
              onChange={(e) => setApplyAfterDays(e.target.value)}
              data-testid="policy-apply-after-days"
            />
          </label>
          {kind === "compound_percent" ? (
            <label className="block text-sm">
              Compound interval (days)
              <Input
                type="number"
                min={1}
                value={compoundIntervalDays}
                onChange={(e) => setCompoundIntervalDays(e.target.value)}
                data-testid="policy-compound-interval-days"
              />
            </label>
          ) : null}
        </div>
        <label className="block text-sm">
          Notes
          <textarea
            className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            data-testid="policy-notes"
          />
        </label>
      </div>

      <div className="flex gap-2">
        <Button
          disabled={submitting}
          onClick={() => void submit()}
          data-testid="save-policy-btn"
        >
          {submitting ? "Saving…" : "Save policy"}
        </Button>
        <Button
          variant="outline"
          disabled={submitting}
          onClick={() => navigate("/late-fee-policies")}
        >
          Cancel
        </Button>
      </div>
    </section>
  );
}
