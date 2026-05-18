/**
 * `/banking/reconciliation/:id` — clear/unclear items, see the running
 * difference update instantly, recompute, finalize.
 *
 * Math contract:
 *   difference = statement_ending_balance - sum(cleared_items.amount)
 *
 * Decimal arithmetic is done in fixed-point (cents) to avoid float drift —
 * the server is still the source of truth for the actual finalize gate.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type Recon = components["schemas"]["BankReconciliationResponse"];
type Tx = components["schemas"]["BankTransactionResponse"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

function toCents(s: string | null | undefined): number {
  if (!s) return 0;
  const n = Number.parseFloat(s);
  if (!Number.isFinite(n)) return 0;
  return Math.round(n * 100);
}

function fromCents(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  const dollars = Math.trunc(abs / 100);
  const remainder = (abs % 100).toString().padStart(2, "0");
  return `${sign}${dollars}.${remainder}`;
}

export function ReconciliationBoardPage() {
  const { id } = useParams();
  const reconId = id ?? "";
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [recon, setRecon] = useState<Recon | null>(null);
  const [txs, setTxs] = useState<Record<string, Tx>>({});
  // Local cleared-state mirror — server is the source of truth on POST,
  // but we flip locally so the running difference updates instantly.
  const [clearedLocal, setClearedLocal] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyItem, setBusyItem] = useState<string | null>(null);
  const [finalizing, setFinalizing] = useState(false);

  const load = useCallback(async () => {
    if (!reconId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.get<Recon>(
        `/api/v1/bank-reconciliations/${reconId}`,
      );
      const r = res.data;
      setRecon(r);
      const initial: Record<string, boolean> = {};
      for (const item of r.items ?? []) initial[item.id] = item.is_cleared;
      setClearedLocal(initial);
      // Fetch matching bank transactions so we can render description/amount.
      const txIds = (r.items ?? []).map((i) => i.bank_transaction_id);
      if (txIds.length > 0) {
        const txRes = await api.get("/api/v1/bank-transactions", {
          params: { account_id: r.account_id },
        });
        const txMap: Record<string, Tx> = {};
        for (const t of txRes.data.items) {
          if (txIds.includes(t.id)) txMap[t.id] = t;
        }
        setTxs(txMap);
      } else {
        setTxs({});
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : "Failed to load reconciliation.",
      );
    } finally {
      setLoading(false);
    }
  }, [reconId]);

  useEffect(() => {
    void load();
  }, [load]);

  const finalized = recon?.state === "finalized";

  // Client-side running difference: stmt - sum(cleared.amount).
  const differenceCents = useMemo(() => {
    if (!recon) return 0;
    const stmt = toCents(recon.statement_ending_balance);
    let clearedSum = 0;
    for (const item of recon.items ?? []) {
      if (clearedLocal[item.id]) {
        const tx = txs[item.bank_transaction_id];
        if (tx) clearedSum += toCents(tx.amount);
      }
    }
    return stmt - clearedSum;
  }, [recon, clearedLocal, txs]);

  const canFinalize = canWrite && !finalized && differenceCents === 0;

  async function toggle(itemId: string, nextCleared: boolean) {
    if (finalized) return;
    setBusyItem(itemId);
    setError(null);
    // Optimistic flip.
    setClearedLocal((prev) => ({ ...prev, [itemId]: nextCleared }));
    try {
      const path = nextCleared ? "clear" : "unclear";
      await apiClient.post(
        `/api/v1/bank-reconciliations/${reconId}/items/${itemId}/${path}`,
      );
    } catch (err: unknown) {
      // Revert on failure.
      setClearedLocal((prev) => ({ ...prev, [itemId]: !nextCleared }));
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not update item.");
    } finally {
      setBusyItem(null);
    }
  }

  async function recompute() {
    try {
      await apiClient.post(`/api/v1/bank-reconciliations/${reconId}/recompute`);
      await load();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Recompute failed.");
    }
  }

  async function finalize() {
    setFinalizing(true);
    setError(null);
    try {
      await apiClient.post(`/api/v1/bank-reconciliations/${reconId}/finalize`);
      await load();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Finalize failed.");
    } finally {
      setFinalizing(false);
    }
  }

  if (loading && !recon) {
    return <p className="p-4 text-sm text-muted-foreground">Loading…</p>;
  }
  if (!recon) {
    return error ? (
      <p role="alert" className="p-4 text-sm text-destructive">
        {error}
      </p>
    ) : null;
  }

  return (
    <section className="space-y-4">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">Reconciliation</h1>
          <p className="text-sm text-muted-foreground">
            {recon.period_start} → {recon.period_end}
          </p>
        </div>
        {finalized ? (
          <span
            className="rounded bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-800"
            data-testid="finalized-badge"
          >
            Finalized
          </span>
        ) : null}
      </header>

      <div className="grid grid-cols-3 gap-3 rounded-lg border border-border p-4 text-sm">
        <div>
          <div className="text-xs uppercase text-muted-foreground">
            Statement
          </div>
          <div className="font-mono">{recon.statement_ending_balance}</div>
        </div>
        <div>
          <div className="text-xs uppercase text-muted-foreground">Book</div>
          <div className="font-mono">{recon.book_ending_balance ?? "—"}</div>
        </div>
        <div>
          <div className="text-xs uppercase text-muted-foreground">
            Difference
          </div>
          <div
            className={
              "font-mono " +
              (differenceCents === 0 ? "text-emerald-700" : "text-destructive")
            }
            data-testid="recon-difference"
          >
            {fromCents(differenceCents)}
          </div>
        </div>
      </div>

      {error ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <div className="flex gap-2">
        {canWrite && !finalized ? (
          <Button
            variant="outline"
            onClick={() => void recompute()}
            data-testid="recon-recompute"
          >
            Recompute
          </Button>
        ) : null}
        {canWrite && !finalized ? (
          <Button
            onClick={() => void finalize()}
            disabled={!canFinalize || finalizing}
            data-testid="recon-finalize"
          >
            {finalizing ? "Finalizing…" : "Finalize"}
          </Button>
        ) : null}
      </div>

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Cleared</th>
            <th className="py-2 pr-2">Date</th>
            <th className="py-2 pr-2">Description</th>
            <th className="py-2 pr-2 text-right">Amount</th>
          </tr>
        </thead>
        <tbody>
          {(recon.items ?? []).length === 0 ? (
            <tr>
              <td colSpan={4} className="py-4 text-center text-muted-foreground">
                No items in this period.
              </td>
            </tr>
          ) : (
            (recon.items ?? []).map((item) => {
              const tx = txs[item.bank_transaction_id];
              return (
                <tr
                  key={item.id}
                  className="border-b border-border/50"
                  data-testid={`recon-item-${item.id}`}
                >
                  <td className="py-2 pr-2">
                    <input
                      type="checkbox"
                      checked={clearedLocal[item.id] ?? false}
                      disabled={finalized || busyItem === item.id || !canWrite}
                      onChange={(e) => void toggle(item.id, e.target.checked)}
                      data-testid={`recon-check-${item.id}`}
                    />
                  </td>
                  <td className="py-2 pr-2">{tx?.occurred_on ?? "—"}</td>
                  <td className="py-2 pr-2">{tx?.description ?? "—"}</td>
                  <td className="py-2 pr-2 text-right font-mono">
                    {tx?.amount ?? "—"}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </section>
  );
}
