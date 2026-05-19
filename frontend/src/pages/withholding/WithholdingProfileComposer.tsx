/**
 * `/withholding-profiles/new` — create a withholding profile
 * (Phase 9.10a, #162).
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { AccountPicker } from "@/components/ar/AccountPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type WithholdingProfileCreate =
  components["schemas"]["WithholdingProfileCreate"];

export function WithholdingProfileComposerPage() {
  const navigate = useNavigate();

  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [jurisdiction, setJurisdiction] = useState("US");
  const [rate, setRate] = useState("0.07");
  const [thresholdPerYear, setThresholdPerYear] = useState("");
  const [formKind, setFormKind] = useState("1099-NEC");
  const [liabilityAccountId, setLiabilityAccountId] = useState("");
  const [notes, setNotes] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!code.trim() || !name.trim() || !jurisdiction.trim() || !liabilityAccountId) {
      setError("code, name, jurisdiction, and liability account are required");
      return;
    }
    const body: WithholdingProfileCreate = {
      code: code.trim(),
      name: name.trim(),
      jurisdiction: jurisdiction.trim(),
      rate,
      liability_account_id: liabilityAccountId,
      threshold_per_year: thresholdPerYear || null,
      form_kind: formKind || null,
      notes: notes || null,
    };
    setSubmitting(true);
    try {
      const res = await api.post("/api/v1/withholding-profiles", body);
      navigate(`/withholding-profiles?highlight=${res.data.id}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response
        ?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to create profile.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={onSubmit}
      data-testid="withholding-form"
    >
      <header>
        <h1 className="text-xl font-semibold">New withholding profile</h1>
      </header>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="block text-xs">
          Code
          <Input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="US-1099-NEC"
            data-testid="wh-code"
            required
          />
        </label>
        <label className="block text-xs">
          Name
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            data-testid="wh-name"
            required
          />
        </label>
        <label className="block text-xs">
          Jurisdiction
          <Input
            value={jurisdiction}
            onChange={(e) => setJurisdiction(e.target.value)}
            data-testid="wh-juris"
            required
          />
        </label>
        <label className="block text-xs">
          Form kind
          <Input
            value={formKind}
            onChange={(e) => setFormKind(e.target.value)}
            placeholder="1099-NEC / 1099-MISC / T4A"
            data-testid="wh-form-kind"
          />
        </label>
        <label className="block text-xs">
          Rate (0.0 – 1.0)
          <Input
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            inputMode="decimal"
            data-testid="wh-rate"
            required
          />
        </label>
        <label className="block text-xs">
          Annual threshold (optional)
          <Input
            value={thresholdPerYear}
            onChange={(e) => setThresholdPerYear(e.target.value)}
            inputMode="decimal"
            placeholder="600.00"
            data-testid="wh-threshold"
          />
        </label>
        <label className="block text-xs sm:col-span-2">
          Liability account (Cr at payment)
          <AccountPicker
            value={liabilityAccountId}
            onChange={setLiabilityAccountId}
            filterType="liability"
            data-testid="wh-liability"
          />
        </label>
      </div>

      <label className="block text-xs">
        Notes
        <textarea
          className="mt-1 min-h-[60px] w-full rounded-md border border-input bg-background p-2 text-sm"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          data-testid="wh-notes"
        />
      </label>

      <div className="flex gap-2">
        <Button type="submit" disabled={submitting} data-testid="wh-submit">
          {submitting ? "Saving…" : "Create profile"}
        </Button>
        <Button
          variant="ghost"
          type="button"
          onClick={() => navigate("/withholding-profiles")}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
