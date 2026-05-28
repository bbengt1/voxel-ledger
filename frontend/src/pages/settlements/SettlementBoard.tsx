/**
 * `/settlements/:id` — matcher board (Phase 9.10b, #162).
 *
 * Two-column layout: lines on the left with state filters + per-row
 * actions (match / unmatch / ignore); a small "manual match" panel on
 * the right that takes a sale-id. The bottom action bar offers Run
 * auto-match and Post payout JE (disabled until every sale/refund
 * line is matched).
 */
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type SettlementWithLines = components["schemas"]["SettlementWithLinesResponse"];
type SettlementResponse = components["schemas"]["SettlementResponse"];
type SettlementLineResponse = components["schemas"]["SettlementLineResponse"];

type StateFilter = "all" | "unmatched" | "matched" | "ignored";

function lineIsBlockingPost(line: SettlementLineResponse): boolean {
  return (
    (line.line_kind === "sale" || line.line_kind === "refund") &&
    line.state === "unmatched"
  );
}

export function SettlementBoardPage() {
  const { id = "" } = useParams<{ id: string }>();
  const [settlement, setSettlement] = useState<SettlementResponse | null>(null);
  const [lines, setLines] = useState<SettlementLineResponse[]>([]);
  const [filter, setFilter] = useState<StateFilter>("unmatched");
  const [selectedLineId, setSelectedLineId] = useState<string | null>(null);
  const [manualSaleId, setManualSaleId] = useState("");
  const [manualRefundId, setManualRefundId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(() => {
    if (!id) return;
    apiClient
      .get<SettlementWithLines>(`/api/v1/settlements/${id}`)
      .then((res) => {
        const data = res.data;
        setSettlement(data.settlement);
        setLines(data.lines);
      })
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } }).response
          ?.data?.detail;
        setError(typeof detail === "string" ? detail : "Failed to load settlement.");
      });
  }, [id]);

  useEffect(() => {
    reload();
  }, [reload]);

  async function runAutoMatch() {
    setBusy(true);
    setError(null);
    try {
      await apiClient.post(`/api/v1/settlements/${id}/match-now`, {});
      reload();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response
        ?.data?.detail;
      setError(typeof detail === "string" ? detail : "Auto-match failed.");
    } finally {
      setBusy(false);
    }
  }

  async function postSettlement() {
    setBusy(true);
    setError(null);
    try {
      await apiClient.post(`/api/v1/settlements/${id}/post`, {});
      reload();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response
        ?.data?.detail;
      setError(typeof detail === "string" ? detail : "Post failed.");
    } finally {
      setBusy(false);
    }
  }

  async function unmatchLine(lineId: string) {
    setBusy(true);
    try {
      await apiClient.post(`/api/v1/settlements/${id}/lines/${lineId}/unmatch`, {});
      reload();
    } finally {
      setBusy(false);
    }
  }

  async function ignoreLine(lineId: string) {
    setBusy(true);
    try {
      await apiClient.post(`/api/v1/settlements/${id}/lines/${lineId}/ignore`, {});
      reload();
    } finally {
      setBusy(false);
    }
  }

  async function manualMatch() {
    if (!selectedLineId) return;
    setBusy(true);
    setError(null);
    const body: Record<string, string | null> = {};
    if (manualSaleId) body["sale_id"] = manualSaleId;
    if (manualRefundId) body["refund_id"] = manualRefundId;
    try {
      await apiClient.post(
        `/api/v1/settlements/${id}/lines/${selectedLineId}/match`,
        body,
      );
      setManualSaleId("");
      setManualRefundId("");
      reload();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } }).response
        ?.data?.detail;
      setError(typeof detail === "string" ? detail : "Match failed.");
    } finally {
      setBusy(false);
    }
  }

  if (!settlement) {
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

  const unmatchedBlocking = lines.filter(lineIsBlockingPost).length;
  const canPost =
    settlement.state !== "posted" &&
    settlement.state !== "cancelled" &&
    unmatchedBlocking === 0;

  const filteredLines = lines.filter((line) =>
    filter === "all" ? true : line.state === filter,
  );

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">
            {settlement.settlement_number}
          </h1>
          <p className="text-xs text-muted-foreground">
            {settlement.period_start} → {settlement.period_end} ·{" "}
            <span className="rounded bg-muted px-1.5 py-0.5">
              {settlement.state}
            </span>
          </p>
        </div>
        <div className="text-right text-xs">
          <div>gross {settlement.gross_amount}</div>
          <div>fees {settlement.fee_amount}</div>
          <div>refunds {settlement.refund_amount}</div>
          <div className="font-medium">payout {settlement.payout_amount}</div>
        </div>
      </header>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
        <div className="flex flex-col gap-3">
          <div className="flex gap-2">
            {(["unmatched", "matched", "ignored", "all"] as StateFilter[]).map(
              (f) => (
                <button
                  key={f}
                  type="button"
                  className={`rounded border px-2 py-1 text-xs ${filter === f ? "border-primary bg-primary/10" : "border-border"}`}
                  onClick={() => setFilter(f)}
                  data-testid={`filter-${f}`}
                >
                  {f}
                </button>
              ),
            )}
          </div>

          <table className="w-full table-fixed border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
                <th className="w-10 py-2 pr-2">#</th>
                <th className="py-2 pr-2">Kind</th>
                <th className="py-2 pr-2">Order id</th>
                <th className="py-2 pr-2">Amount</th>
                <th className="py-2 pr-2">State</th>
                <th className="py-2 pr-2"></th>
              </tr>
            </thead>
            <tbody>
              {filteredLines.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-4 text-center text-muted-foreground">
                    No lines match this filter.
                  </td>
                </tr>
              ) : (
                filteredLines.map((line) => (
                  <tr
                    key={line.id}
                    data-testid={`settlement-line-${line.id}`}
                    className={
                      "border-b border-border/50 " +
                      (selectedLineId === line.id ? "bg-accent/40" : "")
                    }
                  >
                    <td className="py-1 pr-2 font-mono text-xs">{line.line_number}</td>
                    <td className="py-1 pr-2 text-xs">{line.line_kind}</td>
                    <td className="py-1 pr-2 text-xs">
                      {line.external_order_id ?? "—"}
                    </td>
                    <td className="py-1 pr-2">{line.amount}</td>
                    <td className="py-1 pr-2 text-xs">
                      <span className="rounded bg-muted px-1.5 py-0.5">
                        {line.state}
                      </span>
                    </td>
                    <td className="py-1 pr-2 text-right text-xs">
                      <button
                        type="button"
                        className="px-1 underline"
                        onClick={() => setSelectedLineId(line.id)}
                        data-testid={`select-${line.id}`}
                      >
                        select
                      </button>
                      {line.state === "matched" ? (
                        <button
                          type="button"
                          className="px-1"
                          onClick={() => unmatchLine(line.id)}
                          data-testid={`unmatch-${line.id}`}
                        >
                          unmatch
                        </button>
                      ) : null}
                      {line.state === "unmatched" ? (
                        <button
                          type="button"
                          className="px-1"
                          onClick={() => ignoreLine(line.id)}
                          data-testid={`ignore-${line.id}`}
                        >
                          ignore
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <aside className="flex flex-col gap-3 rounded border border-border p-3 text-sm">
          <h2 className="font-medium">Manual match</h2>
          {selectedLineId ? (
            <>
              <p className="text-xs text-muted-foreground">
                Selected line: <span className="font-mono">{selectedLineId.slice(0, 8)}…</span>
              </p>
              <label className="block text-xs">
                Sale id
                <Input
                  value={manualSaleId}
                  onChange={(e) => {
                    setManualSaleId(e.target.value);
                    if (e.target.value) setManualRefundId("");
                  }}
                  data-testid="manual-sale-id"
                />
              </label>
              <label className="block text-xs">
                Refund id
                <Input
                  value={manualRefundId}
                  onChange={(e) => {
                    setManualRefundId(e.target.value);
                    if (e.target.value) setManualSaleId("");
                  }}
                  data-testid="manual-refund-id"
                />
              </label>
              <Button
                type="button"
                onClick={manualMatch}
                disabled={busy || (!manualSaleId && !manualRefundId)}
                data-testid="manual-match-submit"
              >
                Match line
              </Button>
            </>
          ) : (
            <p className="text-xs text-muted-foreground">
              Select a line from the list to manually match it.
            </p>
          )}
        </aside>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
        <Button onClick={runAutoMatch} disabled={busy} data-testid="auto-match">
          Run auto-match
        </Button>
        <Button
          onClick={postSettlement}
          disabled={busy || !canPost}
          data-testid="post-settlement"
        >
          Post payout JE
        </Button>
        {!canPost && settlement.state !== "posted" ? (
          <span className="text-xs text-muted-foreground">
            {unmatchedBlocking} sale/refund line(s) still need to be matched
            before posting.
          </span>
        ) : null}
      </div>
    </section>
  );
}
