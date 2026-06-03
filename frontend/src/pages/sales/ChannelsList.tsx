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
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
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
  taxProfileId: string;
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
    taxProfileId: "",
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
    taxProfileId: c.tax_profile_id ?? "",
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
  const [taxProfiles, setTaxProfiles] = useState<
    { id: string; name: string; jurisdiction: string }[]
  >([]);

  // Load active tax profiles once for the picker.
  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<{ items: typeof taxProfiles }>("/api/v1/tax-profiles", {
        params: { active: true },
      })
      .then((res) => {
        if (!cancelled) setTaxProfiles(res.data.items);
      })
      .catch(() => {
        /* non-fatal — picker just shows "None". */
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
          tax_profile_id: draft.taxProfileId || null,
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
        if (draft.taxProfileId) body.tax_profile_id = draft.taxProfileId;
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

  const columns: DataTableColumn<SalesChannelResponse>[] = [
    { key: "name", header: "Name", isPrimary: true, cell: (c) => c.name },
    {
      key: "slug",
      header: "Slug",
      cell: (c) => <span className="font-mono text-xs">{c.slug}</span>,
    },
    { key: "kind", header: "Kind", cell: (c) => c.kind },
    { key: "fee_model", header: "Fee model", cell: (c) => c.fee_model },
    { key: "active", header: "Active", cell: (c) => (c.is_active ? "Yes" : "No") },
    {
      key: "actions",
      header: "Action",
      align: "right",
      cardFullWidth: true,
      cell: (c) =>
        canWrite ? (
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
        ) : null,
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Sales channels"
        actions={
          canWrite ? (
            <Button onClick={() => setDraft(emptyDraft())} data-testid="new-channel-btn">
              New channel
            </Button>
          ) : null
        }
      />

      {error ? (
        <div role="alert" className="text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(c) => c.id}
        loading={loading && items.length === 0}
        emptyMessage="No channels yet."
        minWidthClassName="min-w-[680px]"
      />

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
            <label className="col-span-2 block text-sm">
              Tax profile
              <select
                className="mt-1 block w-full rounded border border-input bg-background px-2 py-1 text-sm"
                value={draft.taxProfileId}
                onChange={(e) =>
                  setDraft({ ...draft, taxProfileId: e.target.value })
                }
                data-testid="channel-tax-profile"
              >
                <option value="">— None (no tax computed) —</option>
                {taxProfiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.jurisdiction})
                  </option>
                ))}
              </select>
              <span className="mt-1 block text-xs text-muted-foreground">
                When set, POS and other checkout flows compute tax from
                this profile's rate ladder. Manage profiles under
                Accounting → Tax profiles.
              </span>
            </label>
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
