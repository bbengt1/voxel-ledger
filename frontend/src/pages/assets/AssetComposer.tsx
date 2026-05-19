/**
 * `/assets/new` — acquire a fixed asset (Phase 9.10a, #162).
 *
 * Acquisition is same-TX on the backend (row + JE + schedule). The form
 * posts to ``POST /api/v1/fixed-assets`` and on success navigates to
 * the new asset's detail page.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { AccountPicker } from "@/components/ar/AccountPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type AcquireRequest = components["schemas"]["FixedAssetAcquireRequest"];

const TODAY = new Date().toISOString().slice(0, 10);

export function AssetComposerPage() {
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [kind, setKind] = useState<AcquireRequest["kind"]>("tangible");
  const [assetClass, setAssetClass] =
    useState<AcquireRequest["asset_class"]>("computer");
  const [acquiredOn, setAcquiredOn] = useState(TODAY);
  const [acquisitionCost, setAcquisitionCost] = useState("");
  const [salvageValue, setSalvageValue] = useState("0");
  const [usefulLifeMonths, setUsefulLifeMonths] = useState("36");
  const [depreciationMethod, setDepreciationMethod] =
    useState<AcquireRequest["depreciation_method"]>("straight_line");
  const [assetAccountId, setAssetAccountId] = useState("");
  const [accumDepAccountId, setAccumDepAccountId] = useState("");
  const [depExpAccountId, setDepExpAccountId] = useState("");
  const [contraAccountId, setContraAccountId] = useState("");
  const [serialNumber, setSerialNumber] = useState("");
  const [notes, setNotes] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!name.trim()) return setError("name is required");
    if (!acquisitionCost) return setError("acquisition cost is required");
    if (!assetAccountId || !accumDepAccountId || !depExpAccountId) {
      return setError("asset / accumulated depreciation / expense accounts are required");
    }
    if (!contraAccountId) {
      return setError("contra (bank / AP) account is required for cash acquisitions");
    }

    const body: AcquireRequest = {
      name: name.trim(),
      kind,
      asset_class: assetClass,
      acquired_on: acquiredOn,
      acquisition_cost: acquisitionCost,
      salvage_value: salvageValue || "0",
      useful_life_months: Number(usefulLifeMonths),
      depreciation_method: depreciationMethod,
      asset_account_id: assetAccountId,
      accumulated_depreciation_account_id: accumDepAccountId,
      depreciation_expense_account_id: depExpAccountId,
      contra_account_id: contraAccountId,
      serial_number: serialNumber || null,
      vendor_id: null,
      acquisition_bill_id: null,
      notes: notes || null,
    };

    setSubmitting(true);
    try {
      const res = await api.post("/api/v1/fixed-assets", body);
      navigate(`/assets/${res.data.id}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response
        ?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to acquire asset.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={onSubmit} data-testid="asset-form">
      <header>
        <h1 className="text-xl font-semibold">Acquire asset</h1>
      </header>

      {error ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="block text-xs">
          Name
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            data-testid="asset-name"
            required
          />
        </label>
        <label className="block text-xs">
          Serial number
          <Input
            value={serialNumber}
            onChange={(e) => setSerialNumber(e.target.value)}
            data-testid="asset-serial"
          />
        </label>
        <label className="block text-xs">
          Kind
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={kind}
            onChange={(e) => setKind(e.target.value as AcquireRequest["kind"])}
            data-testid="asset-kind"
          >
            <option value="tangible">Tangible</option>
            <option value="intangible">Intangible</option>
          </select>
        </label>
        <label className="block text-xs">
          Class
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={assetClass}
            onChange={(e) =>
              setAssetClass(e.target.value as AcquireRequest["asset_class"])
            }
            data-testid="asset-class"
          >
            <option value="machine">Machine</option>
            <option value="printer">Printer</option>
            <option value="computer">Computer</option>
            <option value="furniture">Furniture</option>
            <option value="vehicle">Vehicle</option>
            <option value="software">Software</option>
            <option value="intellectual_property">IP</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label className="block text-xs">
          Acquired on
          <Input
            type="date"
            value={acquiredOn}
            onChange={(e) => setAcquiredOn(e.target.value)}
            data-testid="asset-acquired-on"
          />
        </label>
        <label className="block text-xs">
          Acquisition cost
          <Input
            value={acquisitionCost}
            onChange={(e) => setAcquisitionCost(e.target.value)}
            data-testid="asset-cost"
            inputMode="decimal"
            required
          />
        </label>
        <label className="block text-xs">
          Salvage value
          <Input
            value={salvageValue}
            onChange={(e) => setSalvageValue(e.target.value)}
            data-testid="asset-salvage"
            inputMode="decimal"
          />
        </label>
        <label className="block text-xs">
          Useful life (months)
          <Input
            type="number"
            min={1}
            value={usefulLifeMonths}
            onChange={(e) => setUsefulLifeMonths(e.target.value)}
            data-testid="asset-life"
          />
        </label>
        <label className="block text-xs">
          Depreciation method
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={depreciationMethod}
            onChange={(e) =>
              setDepreciationMethod(
                e.target.value as AcquireRequest["depreciation_method"],
              )
            }
            data-testid="asset-method"
          >
            <option value="straight_line">Straight line</option>
            <option value="declining_balance_200">Declining balance 200%</option>
            <option value="declining_balance_150">Declining balance 150%</option>
            <option value="none">None</option>
          </select>
        </label>
      </div>

      <fieldset className="grid grid-cols-1 gap-3 sm:grid-cols-2 rounded border border-border p-3">
        <legend className="px-1 text-xs uppercase text-muted-foreground">
          Posting accounts
        </legend>
        <label className="block text-xs">
          Asset account (Dr)
          <AccountPicker
            value={assetAccountId}
            onChange={setAssetAccountId}
            filterType="asset"
            data-testid="picker-asset"
          />
        </label>
        <label className="block text-xs">
          Accumulated depreciation (contra-asset)
          <AccountPicker
            value={accumDepAccountId}
            onChange={setAccumDepAccountId}
            filterType="asset"
            data-testid="picker-accum"
          />
        </label>
        <label className="block text-xs">
          Depreciation expense (Dr at posting)
          <AccountPicker
            value={depExpAccountId}
            onChange={setDepExpAccountId}
            filterType="expense"
            data-testid="picker-dep-exp"
          />
        </label>
        <label className="block text-xs">
          Contra (Bank / AP)
          <AccountPicker
            value={contraAccountId}
            onChange={setContraAccountId}
            data-testid="picker-contra"
          />
        </label>
      </fieldset>

      <label className="block text-xs">
        Notes
        <textarea
          className="mt-1 min-h-[60px] w-full rounded-md border border-input bg-background p-2 text-sm"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          data-testid="asset-notes"
        />
      </label>

      <div className="flex gap-2">
        <Button type="submit" disabled={submitting} data-testid="asset-submit">
          {submitting ? "Acquiring…" : "Acquire asset"}
        </Button>
        <Button variant="ghost" type="button" onClick={() => navigate("/assets")}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
