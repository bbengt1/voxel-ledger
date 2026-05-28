/**
 * `/assets/:id` — fixed-asset detail with Schedule + Disposal tabs
 * (Phase 9.10a, #162).
 */
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { AccountPicker } from "@/components/ar/AccountPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type AssetResponse = components["schemas"]["FixedAssetResponse"];
type ScheduleResponse = components["schemas"]["DepreciationScheduleResponse"];
type DisposalRequest = components["schemas"]["FixedAssetDisposalRequest"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

type Tab = "schedule" | "disposal";

export function AssetDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [asset, setAsset] = useState<AssetResponse | null>(null);
  const [schedule, setSchedule] = useState<ScheduleResponse | null>(null);
  const [tab, setTab] = useState<Tab>("schedule");
  const [error, setError] = useState<string | null>(null);

  // Disposal form state
  const [disposedOn, setDisposedOn] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [disposalKind, setDisposalKind] = useState<DisposalRequest["kind"]>("sale");
  const [proceedsAmount, setProceedsAmount] = useState("0");
  const [proceedsAccountId, setProceedsAccountId] = useState("");
  const [gainLossAccountId, setGainLossAccountId] = useState("");
  const [disposalNotes, setDisposalNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function loadAsset() {
    apiClient
      .get<AssetResponse>(`/api/v1/fixed-assets/${id}`)
      .then((res) => setAsset(res.data))
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } }).response
          ?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load asset.");
      });
  }

  useEffect(() => {
    if (!id) return;
    loadAsset();
    apiClient
      .get<ScheduleResponse>(`/api/v1/fixed-assets/${id}/depreciation-schedule`)
      .then((res) => setSchedule(res.data))
      .catch(() => {
        /* non-fatal */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function onDispose(e: React.FormEvent) {
    e.preventDefault();
    if (!asset) return;
    setError(null);
    if (!gainLossAccountId) {
      setError("gain/loss account is required");
      return;
    }
    const proceedsNum = Number(proceedsAmount || "0");
    if (proceedsNum > 0 && !proceedsAccountId) {
      setError("proceeds account is required when proceeds > 0");
      return;
    }

    const body: DisposalRequest = {
      disposed_on: disposedOn,
      kind: disposalKind,
      proceeds_amount: proceedsAmount || "0",
      proceeds_account_id: proceedsNum > 0 ? proceedsAccountId : null,
      gain_loss_account_id: gainLossAccountId,
      notes: disposalNotes || null,
    };

    setSubmitting(true);
    try {
      await apiClient.post(`/api/v1/fixed-assets/${id}/dispose`, body);
      loadAsset();
      setTab("schedule");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response
        ?.data?.detail;
      setError(typeof detail === "string" ? detail : "Disposal failed.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!asset) {
    return (
      <section className="flex flex-col gap-4">
        {error ? (
          <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        ) : (
          <p className="text-muted-foreground">Loading…</p>
        )}
      </section>
    );
  }

  const isDisposed = asset.state !== "active";

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">{asset.name}</h1>
          <p className="text-xs text-muted-foreground">
            {asset.asset_number} · {asset.kind} · {asset.asset_class} ·{" "}
            <span className="rounded bg-muted px-1.5 py-0.5">{asset.state}</span>
          </p>
        </div>
        <div className="text-right text-xs">
          <div>cost {asset.acquisition_cost}</div>
          <div>life {asset.useful_life_months} mo · {asset.depreciation_method}</div>
          <div>acquired {asset.acquired_on}</div>
        </div>
      </header>

      {error ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <div className="flex gap-2 border-b border-border">
        <button
          type="button"
          className={`px-3 py-1 text-sm ${tab === "schedule" ? "border-b-2 border-primary font-medium" : "text-muted-foreground"}`}
          onClick={() => setTab("schedule")}
          data-testid="tab-schedule"
        >
          Schedule
        </button>
        <button
          type="button"
          className={`px-3 py-1 text-sm ${tab === "disposal" ? "border-b-2 border-primary font-medium" : "text-muted-foreground"}`}
          onClick={() => setTab("disposal")}
          data-testid="tab-disposal"
          disabled={isDisposed}
        >
          Disposal {isDisposed ? "(done)" : null}
        </button>
      </div>

      {tab === "schedule" ? (
        <table className="w-full table-fixed border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
              <th className="py-2 pr-2">#</th>
              <th className="py-2 pr-2">Period end</th>
              <th className="py-2 pr-2">Opening</th>
              <th className="py-2 pr-2">Depreciation</th>
              <th className="py-2 pr-2">Closing</th>
              <th className="py-2 pr-2">State</th>
            </tr>
          </thead>
          <tbody>
            {schedule && schedule.entries.length ? (
              schedule.entries.map((entry) => (
                <tr key={entry.id} className="border-b border-border/50">
                  <td className="py-1 pr-2 font-mono text-xs">{entry.period_index}</td>
                  <td className="py-1 pr-2">{entry.period_end}</td>
                  <td className="py-1 pr-2">{entry.opening_book_value}</td>
                  <td className="py-1 pr-2">{entry.depreciation_amount}</td>
                  <td className="py-1 pr-2">{entry.closing_book_value}</td>
                  <td className="py-1 pr-2 text-xs">
                    <span className="rounded bg-muted px-1.5 py-0.5">
                      {entry.state}
                    </span>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} className="py-4 text-center text-muted-foreground">
                  No schedule entries.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      ) : null}

      {tab === "disposal" && !isDisposed ? (
        <form className="flex flex-col gap-3" onSubmit={onDispose} data-testid="disposal-form">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="block text-xs">
              Disposed on
              <Input
                type="date"
                value={disposedOn}
                onChange={(e) => setDisposedOn(e.target.value)}
                data-testid="disposal-date"
              />
            </label>
            <label className="block text-xs">
              Kind
              <select
                className="mt-1 h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                value={disposalKind}
                onChange={(e) =>
                  setDisposalKind(e.target.value as DisposalRequest["kind"])
                }
                data-testid="disposal-kind"
              >
                <option value="sale">Sale</option>
                <option value="scrap">Scrap</option>
                <option value="writeoff">Writeoff</option>
                <option value="donation">Donation</option>
              </select>
            </label>
            <label className="block text-xs">
              Proceeds amount
              <Input
                value={proceedsAmount}
                onChange={(e) => setProceedsAmount(e.target.value)}
                data-testid="disposal-proceeds"
                inputMode="decimal"
              />
            </label>
            <label className="block text-xs">
              Proceeds account (Bank / AR)
              <AccountPicker
                value={proceedsAccountId}
                onChange={setProceedsAccountId}
                filterType="asset"
                data-testid="picker-proceeds"
              />
            </label>
            <label className="block text-xs">
              Gain / loss account (P&L)
              <AccountPicker
                value={gainLossAccountId}
                onChange={setGainLossAccountId}
                data-testid="picker-gain-loss"
              />
            </label>
          </div>
          <label className="block text-xs">
            Notes
            <textarea
              className="mt-1 min-h-[60px] w-full rounded-md border border-input bg-background p-2 text-sm"
              value={disposalNotes}
              onChange={(e) => setDisposalNotes(e.target.value)}
              data-testid="disposal-notes"
            />
          </label>
          <div>
            <Button
              type="submit"
              disabled={submitting || !canWrite}
              data-testid="disposal-submit"
            >
              {submitting ? "Disposing…" : "Dispose asset"}
            </Button>
          </div>
        </form>
      ) : null}
      {tab === "disposal" && isDisposed ? (
        <p className="text-sm text-muted-foreground">
          This asset has already been disposed and cannot be disposed again.
        </p>
      ) : null}
    </section>
  );
}
