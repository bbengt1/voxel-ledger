/**
 * `/settlements/import` — multipart CSV import wizard
 * (Phase 9.10b, #162).
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { AccountPicker } from "@/components/ar/AccountPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type SalesChannelResponse = components["schemas"]["SalesChannelResponse"];

const TODAY = new Date().toISOString().slice(0, 10);

export function SettlementImportWizardPage() {
  const navigate = useNavigate();

  const [channels, setChannels] = useState<SalesChannelResponse[]>([]);
  const [channelId, setChannelId] = useState("");
  const [formatKind, setFormatKind] = useState("etsy");
  const [periodStart, setPeriodStart] = useState(TODAY);
  const [periodEnd, setPeriodEnd] = useState(TODAY);
  const [payoutAccountId, setPayoutAccountId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [columnMap, setColumnMap] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get("/api/v1/sales-channels")
      .then((res) => setChannels(res.data.items))
      .catch(() => {
        /* non-fatal */
      });
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!channelId || !payoutAccountId || !file) {
      setError("channel, payout account, and file are required");
      return;
    }

    const fd = new FormData();
    fd.append("channel_id", channelId);
    fd.append("format_kind", formatKind);
    fd.append("period_start", periodStart);
    fd.append("period_end", periodEnd);
    fd.append("payout_account_id", payoutAccountId);
    fd.append("file", file);
    if (columnMap) fd.append("column_map", columnMap);

    setSubmitting(true);
    try {
      const res = await apiClient.post("/api/v1/settlements", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      navigate(`/settlements/${res.data.id}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response
        ?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to import settlement.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={onSubmit} data-testid="settlement-import">
      <header>
        <h1 className="text-xl font-semibold">Import settlement</h1>
      </header>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="block text-xs">
          Channel
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={channelId}
            onChange={(e) => setChannelId(e.target.value)}
            data-testid="import-channel"
            required
          >
            <option value="">Select…</option>
            {channels.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs">
          Format
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
            value={formatKind}
            onChange={(e) => setFormatKind(e.target.value)}
            data-testid="import-format"
          >
            <option value="etsy">Etsy</option>
            <option value="amazon">Amazon</option>
            <option value="shopify">Shopify</option>
            <option value="generic">Generic CSV</option>
          </select>
        </label>
        <label className="block text-xs">
          Period start
          <Input
            type="date"
            value={periodStart}
            onChange={(e) => setPeriodStart(e.target.value)}
            data-testid="import-period-start"
          />
        </label>
        <label className="block text-xs">
          Period end
          <Input
            type="date"
            value={periodEnd}
            onChange={(e) => setPeriodEnd(e.target.value)}
            data-testid="import-period-end"
          />
        </label>
        <label className="block text-xs sm:col-span-2">
          Payout account (Bank)
          <AccountPicker
            value={payoutAccountId}
            onChange={setPayoutAccountId}
            filterType="asset"
            data-testid="import-payout-account"
          />
        </label>
        <label className="block text-xs sm:col-span-2">
          CSV file
          <input
            type="file"
            accept=".csv,text/csv"
            className="mt-1 block w-full text-sm"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            data-testid="import-file"
          />
        </label>
        {formatKind === "generic" ? (
          <label className="block text-xs sm:col-span-2">
            Column map (JSON; ``{`{"date":"Date","amount":"Amount", …}`}``)
            <textarea
              className="mt-1 min-h-[80px] w-full rounded-md border border-input bg-background p-2 text-sm font-mono"
              value={columnMap}
              onChange={(e) => setColumnMap(e.target.value)}
              data-testid="import-column-map"
            />
          </label>
        ) : null}
      </div>

      <div className="flex gap-2">
        <Button type="submit" disabled={submitting} data-testid="import-submit">
          {submitting ? "Importing…" : "Import settlement"}
        </Button>
        <Button variant="ghost" type="button" onClick={() => navigate("/settlements")}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
