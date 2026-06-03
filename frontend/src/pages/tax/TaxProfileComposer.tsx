/**
 * `/tax-profiles/new` and `/tax-profiles/:id` — composer (Phase 9.10b, #162).
 *
 * Profile header + sortable rates table. Rates can be added, edited
 * inline, reordered by ordinal, and removed. is_reverse_charge toggles
 * the whole profile.
 */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { NewAccountDialog } from "@/components/accounting/NewAccountDialog";
import { AccountPicker } from "@/components/ar/AccountPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type TaxProfileResponse = components["schemas"]["TaxProfileResponse"];
type TaxProfileCreate = components["schemas"]["TaxProfileCreate"];
type TaxRateResponse = components["schemas"]["TaxRateResponse"];
type TaxRateCreate = components["schemas"]["TaxRateCreate"];

interface RateDraft {
  id?: string;
  ordinal: number;
  name: string;
  rate: string;
  liability_account_id: string;
  compound_on_previous: boolean;
}

export function TaxProfileComposerPage() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);

  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [jurisdiction, setJurisdiction] = useState("US-CA");
  const [isReverseCharge, setIsReverseCharge] = useState(false);
  const [notes, setNotes] = useState("");
  const [rates, setRates] = useState<RateDraft[]>([]);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Snapshot of the rate ids as they came back from the server so we
  // can compute deletions on save (ids in the snapshot that the user
  // has since removed from the local rates array).
  const [originalRateIds, setOriginalRateIds] = useState<string[]>([]);
  // Index of the rate row whose "+ New" button is currently driving the
  // account-create modal. ``null`` when the modal is closed.
  const [creatingAccountFor, setCreatingAccountFor] = useState<number | null>(
    null,
  );
  // Bump to force AccountPicker to refetch its list after a new account
  // is created, so the freshly-minted row shows up in every picker on
  // the page.
  const [accountsVersion, setAccountsVersion] = useState(0);

  useEffect(() => {
    if (!id) return;
    apiClient
      .get<TaxProfileResponse>(`/api/v1/tax-profiles/${id}`)
      .then((res) => {
        const p = res.data;
        setCode(p.code);
        setName(p.name);
        setJurisdiction(p.jurisdiction);
        setIsReverseCharge(p.is_reverse_charge);
        setNotes(p.notes ?? "");
        const loaded = p.rates.map(
          (r: TaxRateResponse): RateDraft => ({
            id: r.id,
            ordinal: r.ordinal,
            name: r.name,
            rate: String(r.rate),
            liability_account_id: r.liability_account_id,
            compound_on_previous: r.compound_on_previous,
          }),
        );
        setRates(loaded);
        setOriginalRateIds(loaded.map((r) => r.id as string));
      })
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } }).response
          ?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load profile.");
      });
  }, [id]);

  function addRate() {
    setRates((prev) => [
      ...prev,
      {
        ordinal: prev.length,
        name: "",
        rate: "0.05",
        liability_account_id: "",
        compound_on_previous: false,
      },
    ]);
  }

  function updateRate(idx: number, patch: Partial<RateDraft>) {
    setRates((prev) =>
      prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)),
    );
  }

  function removeRate(idx: number) {
    setRates((prev) =>
      prev.filter((_, i) => i !== idx).map((r, i) => ({ ...r, ordinal: i })),
    );
  }

  function moveRate(idx: number, delta: number) {
    setRates((prev) => {
      const next = [...prev];
      const j = idx + delta;
      if (j < 0 || j >= next.length) return prev;
      const cur = next[idx];
      const other = next[j];
      if (!cur || !other) return prev;
      next[idx] = other;
      next[j] = cur;
      return next.map((r, i) => ({ ...r, ordinal: i }));
    });
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!code.trim() || !name.trim() || !jurisdiction.trim()) {
      setError("code, name, and jurisdiction are required");
      return;
    }
    for (const [i, r] of rates.entries()) {
      if (!r.name.trim() || !r.liability_account_id) {
        setError(`rate #${i + 1} needs a name and a liability account`);
        return;
      }
    }

    setSubmitting(true);
    try {
      let profileId = id;
      if (!isEdit) {
        const body: TaxProfileCreate = {
          code: code.trim(),
          name: name.trim(),
          jurisdiction: jurisdiction.trim(),
          is_reverse_charge: isReverseCharge,
          notes: notes || null,
        };
        const res = await api.post("/api/v1/tax-profiles", body);
        profileId = res.data.id;
      } else {
        // Profile-level fields can change on edit (notes, reverse-charge
        // flag, even the name/jurisdiction). Send the updatable subset.
        await apiClient.patch(`/api/v1/tax-profiles/${profileId}`, {
          name: name.trim(),
          jurisdiction: jurisdiction.trim(),
          is_reverse_charge: isReverseCharge,
          notes: notes || null,
        });
      }

      // Diff-and-apply for rates. Order matters: DELETE removed rows
      // first to free their ordinal slots; then PATCH existing rows
      // (which may shift ordinals); finally POST any new rows.
      const currentIds = new Set(rates.map((r) => r.id).filter(Boolean));
      const removedIds = originalRateIds.filter((rid) => !currentIds.has(rid));
      for (const rid of removedIds) {
        await apiClient.delete(`/api/v1/tax-profiles/${profileId}/rates/${rid}`);
      }

      // To avoid transient ordinal collisions when the operator
      // reorders rates, bump every existing rate to a high temporary
      // ordinal first, then PATCH to the real target. With ~10 rates
      // tops this is cheap and unambiguous.
      const existing = rates.filter((r) => r.id);
      if (isEdit && existing.length > 0) {
        for (let i = 0; i < existing.length; i++) {
          const rate = existing[i];
          if (!rate?.id) continue;
          await apiClient.patch(
            `/api/v1/tax-profiles/${profileId}/rates/${rate.id}`,
            { ordinal: 1000 + i },
          );
        }
      }

      for (const r of existing) {
        await apiClient.patch(
          `/api/v1/tax-profiles/${profileId}/rates/${r.id}`,
          {
            ordinal: r.ordinal,
            name: r.name.trim(),
            rate: r.rate,
            liability_account_id: r.liability_account_id,
            compound_on_previous: r.compound_on_previous,
          },
        );
      }

      for (const r of rates) {
        if (r.id) continue;
        const body: TaxRateCreate = {
          ordinal: r.ordinal,
          name: r.name.trim(),
          rate: r.rate,
          liability_account_id: r.liability_account_id,
          compound_on_previous: r.compound_on_previous,
        };
        await apiClient.post(`/api/v1/tax-profiles/${profileId}/rates`, body);
      }

      navigate(`/tax-profiles/${profileId}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response
        ?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to save profile.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={onSubmit} data-testid="tax-profile-form">
      <header>
        <h1 className="text-xl font-semibold">
          {isEdit ? "Tax profile" : "New tax profile"}
        </h1>
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
            placeholder="US-CA-COMBINED"
            data-testid="tp-code"
            required
            disabled={isEdit}
          />
        </label>
        <label className="block text-xs">
          Name
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            data-testid="tp-name"
            required
          />
        </label>
        <label className="block text-xs">
          Jurisdiction
          <Input
            value={jurisdiction}
            onChange={(e) => setJurisdiction(e.target.value)}
            data-testid="tp-juris"
            required
          />
        </label>
        <label className="mt-5 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={isReverseCharge}
            onChange={(e) => setIsReverseCharge(e.target.checked)}
            data-testid="tp-reverse"
          />
          Reverse-charge profile
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

      <fieldset className="rounded border border-border p-3">
        <legend className="px-1 text-xs uppercase text-muted-foreground">
          Rates
        </legend>
        <div className="overflow-x-auto">
        <table className="w-full min-w-[44rem] table-fixed border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
              <th className="w-8 py-2 pr-2">#</th>
              <th className="py-2 pr-2">Name</th>
              <th className="w-20 py-2 pr-2">Rate</th>
              <th className="py-2 pr-2">Liability account</th>
              <th className="w-20 py-2 pr-2">Compound</th>
              <th className="w-28 py-2 pr-2"></th>
            </tr>
          </thead>
          <tbody>
            {rates.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-3 text-center text-muted-foreground">
                  No rates yet.
                </td>
              </tr>
            ) : (
              rates.map((r, i) => (
                <tr key={i} className="border-b border-border/50" data-testid={`tp-rate-row-${i}`}>
                  <td className="py-1 pr-2 font-mono text-xs">{r.ordinal}</td>
                  <td className="py-1 pr-2">
                    <Input
                      value={r.name}
                      onChange={(e) => updateRate(i, { name: e.target.value })}
                      data-testid={`tp-rate-name-${i}`}
                    />
                  </td>
                  <td className="py-1 pr-2">
                    <Input
                      value={r.rate}
                      onChange={(e) => updateRate(i, { rate: e.target.value })}
                      data-testid={`tp-rate-value-${i}`}
                      inputMode="decimal"
                    />
                  </td>
                  <td className="py-1 pr-2">
                    <div className="flex items-center gap-1">
                      <div className="flex-1">
                        <AccountPicker
                          value={r.liability_account_id}
                          onChange={(id) =>
                            updateRate(i, { liability_account_id: id })
                          }
                          filterType="liability"
                          refreshKey={accountsVersion}
                          data-testid={`tp-rate-acct-${i}`}
                        />
                      </div>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => setCreatingAccountFor(i)}
                        data-testid={`tp-rate-acct-new-${i}`}
                      >
                        + New
                      </Button>
                    </div>
                  </td>
                  <td className="py-1 pr-2 text-center">
                    <input
                      type="checkbox"
                      checked={r.compound_on_previous}
                      onChange={(e) =>
                        updateRate(i, { compound_on_previous: e.target.checked })
                      }
                      data-testid={`tp-rate-compound-${i}`}
                    />
                  </td>
                  <td className="py-1 pr-2 text-right text-xs">
                    <button
                      type="button"
                      className="px-1"
                      onClick={() => moveRate(i, -1)}
                      data-testid={`tp-rate-up-${i}`}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className="px-1"
                      onClick={() => moveRate(i, 1)}
                      data-testid={`tp-rate-down-${i}`}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      className="px-1 text-destructive"
                      onClick={() => removeRate(i)}
                      data-testid={`tp-rate-remove-${i}`}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        </div>
        <div className="mt-2">
          <Button type="button" variant="ghost" onClick={addRate} data-testid="tp-add-rate">
            + Add rate
          </Button>
        </div>
      </fieldset>

      <div className="flex gap-2">
        <Button type="submit" disabled={submitting} data-testid="tp-submit">
          {submitting ? "Saving…" : isEdit ? "Save changes" : "Create profile"}
        </Button>
        <Button
          variant="ghost"
          type="button"
          onClick={() => navigate("/tax-profiles")}
        >
          Cancel
        </Button>
      </div>

      <NewAccountDialog
        open={creatingAccountFor !== null}
        onClose={() => setCreatingAccountFor(null)}
        onCreated={(account) => {
          // Slot the new account into the rate row that opened the
          // modal, then refresh every picker on the page so future
          // changes see the new row too.
          if (creatingAccountFor !== null) {
            updateRate(creatingAccountFor, {
              liability_account_id: account.id,
            });
          }
          setAccountsVersion((v) => v + 1);
          setCreatingAccountFor(null);
        }}
        seedName={
          creatingAccountFor !== null
            ? rates[creatingAccountFor]?.name || undefined
            : undefined
        }
        seedType="liability"
      />
    </form>
  );
}
