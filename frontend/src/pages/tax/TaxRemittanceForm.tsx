/**
 * `/tax-remittances/new` — record a tax remittance (Phase 9.10b, #162).
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { AccountPicker } from "@/components/ar/AccountPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type TaxProfileResponse = components["schemas"]["TaxProfileResponse"];
type TaxRemittanceCreate = components["schemas"]["TaxRemittanceCreate"];

const TODAY = new Date().toISOString().slice(0, 10);

export function TaxRemittanceFormPage() {
  const navigate = useNavigate();

  const [profiles, setProfiles] = useState<TaxProfileResponse[]>([]);
  const [profileId, setProfileId] = useState("");
  const [periodStart, setPeriodStart] = useState(TODAY);
  const [periodEnd, setPeriodEnd] = useState(TODAY);
  const [amountPaid, setAmountPaid] = useState("");
  const [paidOn, setPaidOn] = useState(TODAY);
  const [method, setMethod] =
    useState<TaxRemittanceCreate["method"]>("ach");
  const [referenceNumber, setReferenceNumber] = useState("");
  const [bankAccountId, setBankAccountId] = useState("");
  const [notes, setNotes] = useState("");
  const [allowPartial, setAllowPartial] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get("/api/v1/tax-profiles", { params: { active: "true" } })
      .then((res) => setProfiles(res.data.items))
      .catch(() => {
        /* non-fatal */
      });
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!profileId || !amountPaid || !bankAccountId) {
      setError("profile, amount, and bank account are required");
      return;
    }
    const body: TaxRemittanceCreate = {
      profile_id: profileId,
      period_start: periodStart,
      period_end: periodEnd,
      amount_paid: amountPaid,
      paid_on: paidOn,
      method,
      bank_account_id: bankAccountId,
      reference_number: referenceNumber || null,
      notes: notes || null,
      allow_partial: allowPartial,
    };
    setSubmitting(true);
    try {
      await api.post("/api/v1/tax-remittances", body);
      navigate("/tax-remittances");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response
        ?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to record remittance.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={onSubmit} data-testid="remittance-form">
      <header>
        <h1 className="text-xl font-semibold">Record tax remittance</h1>
      </header>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="block text-xs sm:col-span-2">
          Tax profile
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={profileId}
            onChange={(e) => setProfileId(e.target.value)}
            data-testid="remittance-profile"
            required
          >
            <option value="">Select…</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.code} — {p.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs">
          Period start
          <Input
            type="date"
            value={periodStart}
            onChange={(e) => setPeriodStart(e.target.value)}
            data-testid="remittance-period-start"
          />
        </label>
        <label className="block text-xs">
          Period end
          <Input
            type="date"
            value={periodEnd}
            onChange={(e) => setPeriodEnd(e.target.value)}
            data-testid="remittance-period-end"
          />
        </label>
        <label className="block text-xs">
          Amount paid
          <Input
            value={amountPaid}
            onChange={(e) => setAmountPaid(e.target.value)}
            inputMode="decimal"
            data-testid="remittance-amount"
            required
          />
        </label>
        <label className="block text-xs">
          Paid on
          <Input
            type="date"
            value={paidOn}
            onChange={(e) => setPaidOn(e.target.value)}
            data-testid="remittance-paid-on"
          />
        </label>
        <label className="block text-xs">
          Method
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={method}
            onChange={(e) =>
              setMethod(e.target.value as TaxRemittanceCreate["method"])
            }
            data-testid="remittance-method"
          >
            <option value="ach">ACH</option>
            <option value="check">Check</option>
            <option value="wire">Wire</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label className="block text-xs">
          Reference number
          <Input
            value={referenceNumber}
            onChange={(e) => setReferenceNumber(e.target.value)}
            data-testid="remittance-reference"
          />
        </label>
        <label className="block text-xs sm:col-span-2">
          Bank account (Cr)
          <AccountPicker
            value={bankAccountId}
            onChange={setBankAccountId}
            filterType="asset"
            data-testid="remittance-bank"
          />
        </label>
        <label className="mt-1 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={allowPartial}
            onChange={(e) => setAllowPartial(e.target.checked)}
            data-testid="remittance-allow-partial"
          />
          Allow partial payment
        </label>
      </div>

      <label className="block text-xs">
        Notes
        <textarea
          className="mt-1 min-h-[60px] w-full rounded-md border border-input bg-background p-2 text-sm"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </label>

      <div className="flex gap-2">
        <Button type="submit" disabled={submitting} data-testid="remittance-submit">
          {submitting ? "Recording…" : "Record remittance"}
        </Button>
        <Button
          variant="ghost"
          type="button"
          onClick={() => navigate("/tax-remittances")}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
