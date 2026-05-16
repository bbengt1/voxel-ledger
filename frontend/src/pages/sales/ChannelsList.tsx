/**
 * `/sales/channels` — sales channels CRUD page (list + inline create/edit
 * dialog).
 *
 * Phase 6.7a. The fee-model picker drives the visibility of the
 * `fee_percent` and `fee_flat` sub-fields:
 *
 *   - none              → no sub-fields
 *   - flat              → fee_flat
 *   - percent           → fee_percent
 *   - percent_plus_flat → both
 *
 * Default revenue / fee account pickers reuse the existing AccountPicker.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import {
  AccountPicker,
  type AccountOption,
} from "@/components/accounting/AccountPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type SalesChannelResponse = components["schemas"]["SalesChannelResponse"];
type SalesChannelCreate = components["schemas"]["SalesChannelCreate"];
type SalesChannelUpdate = components["schemas"]["SalesChannelUpdate"];
type FeeModel = SalesChannelResponse["fee_model"];
type ChannelKind = SalesChannelResponse["kind"];

const WRITE_ROLES: readonly string[] = ["owner", "bookkeeper"];

const FEE_MODELS: ReadonlyArray<{ value: FeeModel; label: string }> = [
  { value: "none", label: "No fee" },
  { value: "flat", label: "Flat fee" },
  { value: "percent", label: "Percent" },
  { value: "percent_plus_flat", label: "Percent + flat" },
];

const KINDS: ReadonlyArray<{ value: ChannelKind; label: string }> = [
  { value: "pos", label: "POS" },
  { value: "marketplace", label: "Marketplace" },
  { value: "direct_web", label: "Direct web" },
  { value: "wholesale", label: "Wholesale" },
  { value: "other", label: "Other" },
];

interface DraftState {
  id: string | null;
  name: string;
  slug: string;
  kind: ChannelKind;
  feeModel: FeeModel;
  feePercent: string;
  feeFlat: string;
  externalIdFormatHint: string;
  revenueAccount: AccountOption | null;
  feeAccount: AccountOption | null;
}

function emptyDraft(): DraftState {
  return {
    id: null,
    name: "",
    slug: "",
    kind: "direct_web",
    feeModel: "none",
    feePercent: "",
    feeFlat: "",
    externalIdFormatHint: "",
    revenueAccount: null,
    feeAccount: null,
  };
}

function channelToDraft(c: SalesChannelResponse): DraftState {
  return {
    id: c.id,
    name: c.name,
    slug: c.slug,
    kind: c.kind,
    feeModel: c.fee_model,
    feePercent: c.fee_percent ?? "",
    feeFlat: c.fee_flat ?? "",
    externalIdFormatHint: c.external_id_format_hint ?? "",
    revenueAccount: c.default_revenue_account_id
      ? {
          id: c.default_revenue_account_id,
          code: "—",
          name: "(selected)",
          type: "revenue",
        }
      : null,
    feeAccount: c.default_fee_account_id
      ? {
          id: c.default_fee_account_id,
          code: "—",
          name: "(selected)",
          type: "expense",
        }
      : null,
  };
}

export function ChannelsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? WRITE_ROLES.includes(role) : false;

  const [items, setItems] = useState<SalesChannelResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<DraftState | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/api/v1/sales-channels");
      setItems(res.data.items);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to load channels.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  const showPercent = useMemo(
    () =>
      draft?.feeModel === "percent" || draft?.feeModel === "percent_plus_flat",
    [draft?.feeModel],
  );
  const showFlat = useMemo(
    () => draft?.feeModel === "flat" || draft?.feeModel === "percent_plus_flat",
    [draft?.feeModel],
  );

  async function onSubmit() {
    if (!draft) return;
    setSubmitting(true);
    setFormError(null);
    try {
      const trimmedHint = draft.externalIdFormatHint.trim();
      if (draft.id) {
        const body: SalesChannelUpdate = {
          name: draft.name,
          slug: draft.slug,
          kind: draft.kind,
          fee_model: draft.feeModel,
          fee_percent: showPercent && draft.feePercent ? draft.feePercent : null,
          fee_flat: showFlat && draft.feeFlat ? draft.feeFlat : null,
          external_id_format_hint: trimmedHint || null,
          default_revenue_account_id: draft.revenueAccount?.id ?? null,
          default_fee_account_id: draft.feeAccount?.id ?? null,
        };
        await apiClient.patch(`/api/v1/sales-channels/${draft.id}`, body);
      } else {
        const body: SalesChannelCreate = {
          name: draft.name,
          slug: draft.slug,
          kind: draft.kind,
          fee_model: draft.feeModel,
        };
        if (showPercent && draft.feePercent) body.fee_percent = draft.feePercent;
        if (showFlat && draft.feeFlat) body.fee_flat = draft.feeFlat;
        if (trimmedHint) body.external_id_format_hint = trimmedHint;
        if (draft.revenueAccount)
          body.default_revenue_account_id = draft.revenueAccount.id;
        if (draft.feeAccount) body.default_fee_account_id = draft.feeAccount.id;
        await apiClient.post("/api/v1/sales-channels", body);
      }
      setDraft(null);
      await refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setFormError(
        typeof detail === "string" ? detail : "Could not save channel.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function archive(id: string, active: boolean) {
    const path = active ? "archive" : "unarchive";
    try {
      await apiClient.post(`/api/v1/sales-channels/${id}/${path}`);
      await refetch();
    } catch {
      /* surface inline next refetch */
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Sales channels</h1>
        {canWrite ? (
          <Button onClick={() => setDraft(emptyDraft())} data-testid="new-channel-btn">
            New channel
          </Button>
        ) : null}
      </header>

      {error ? (
        <div role="alert" className="text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Name</th>
            <th className="py-2 pr-2">Slug</th>
            <th className="py-2 pr-2">Kind</th>
            <th className="py-2 pr-2">Fee model</th>
            <th className="py-2 pr-2">Active</th>
            <th className="py-2 pr-2 text-right">Action</th>
          </tr>
        </thead>
        <tbody>
          {loading && items.length === 0 ? (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                Loading…
              </td>
            </tr>
          ) : items.length === 0 ? (
            <tr>
              <td colSpan={6} className="py-4 text-center text-muted-foreground">
                No channels yet.
              </td>
            </tr>
          ) : (
            items.map((c) => (
              <tr
                key={c.id}
                className="border-b border-border/50"
                data-testid={`channel-row-${c.id}`}
              >
                <td className="py-2 pr-2">{c.name}</td>
                <td className="py-2 pr-2 font-mono text-xs">{c.slug}</td>
                <td className="py-2 pr-2">{c.kind}</td>
                <td className="py-2 pr-2">{c.fee_model}</td>
                <td className="py-2 pr-2">{c.is_active ? "Yes" : "No"}</td>
                <td className="py-2 pr-2 text-right">
                  {canWrite ? (
                    <div className="inline-flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setDraft(channelToDraft(c))}
                        data-testid={`edit-channel-${c.id}`}
                      >
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => void archive(c.id, c.is_active)}
                        data-testid={`archive-channel-${c.id}`}
                      >
                        {c.is_active ? "Archive" : "Unarchive"}
                      </Button>
                    </div>
                  ) : null}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      {draft ? (
        <div
          className="rounded-lg border border-border p-4"
          data-testid="channel-form"
        >
          <h2 className="text-sm font-semibold">
            {draft.id ? "Edit channel" : "New channel"}
          </h2>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <label className="block text-sm">
              Name
              <Input
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                data-testid="channel-name"
              />
            </label>
            <label className="block text-sm">
              Slug
              <Input
                value={draft.slug}
                onChange={(e) => setDraft({ ...draft, slug: e.target.value })}
                data-testid="channel-slug"
              />
            </label>
            <label className="block text-sm">
              Kind
              <select
                className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                value={draft.kind}
                onChange={(e) =>
                  setDraft({ ...draft, kind: e.target.value as ChannelKind })
                }
                data-testid="channel-kind"
              >
                {KINDS.map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              Fee model
              <select
                className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                value={draft.feeModel}
                onChange={(e) =>
                  setDraft({ ...draft, feeModel: e.target.value as FeeModel })
                }
                data-testid="channel-fee-model"
              >
                {FEE_MODELS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
            </label>
            {showPercent ? (
              <label className="block text-sm" data-testid="channel-fee-percent-wrap">
                Fee percent (e.g. 0.029 = 2.9%)
                <Input
                  type="number"
                  step="0.0001"
                  min={0}
                  value={draft.feePercent}
                  onChange={(e) =>
                    setDraft({ ...draft, feePercent: e.target.value })
                  }
                  data-testid="channel-fee-percent"
                />
              </label>
            ) : null}
            {showFlat ? (
              <label className="block text-sm" data-testid="channel-fee-flat-wrap">
                Fee flat ($/transaction)
                <Input
                  type="number"
                  step="0.01"
                  min={0}
                  value={draft.feeFlat}
                  onChange={(e) =>
                    setDraft({ ...draft, feeFlat: e.target.value })
                  }
                  data-testid="channel-fee-flat"
                />
              </label>
            ) : null}
            <label className="col-span-2 block text-sm">
              External order id format hint
              <Input
                value={draft.externalIdFormatHint}
                onChange={(e) =>
                  setDraft({ ...draft, externalIdFormatHint: e.target.value })
                }
                placeholder="e.g. ETSY-XXXXXX"
                data-testid="channel-ext-hint"
              />
            </label>
            <div className="col-span-2 grid grid-cols-2 gap-3">
              <label className="block text-sm">
                Default revenue account
                <AccountPicker
                  value={draft.revenueAccount}
                  onChange={(opt) =>
                    setDraft({ ...draft, revenueAccount: opt })
                  }
                  data-testid="channel-revenue-account"
                />
              </label>
              <label className="block text-sm">
                Default fee account
                <AccountPicker
                  value={draft.feeAccount}
                  onChange={(opt) => setDraft({ ...draft, feeAccount: opt })}
                  data-testid="channel-fee-account"
                />
              </label>
            </div>
          </div>

          {formError ? (
            <p role="alert" className="mt-2 text-sm text-destructive">
              {formError}
            </p>
          ) : null}

          <div className="mt-3 flex gap-2">
            <Button
              disabled={submitting}
              onClick={() => void onSubmit()}
              data-testid="channel-save"
            >
              {submitting ? "Saving…" : "Save"}
            </Button>
            <Button
              variant="outline"
              disabled={submitting}
              onClick={() => setDraft(null)}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
