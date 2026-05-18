/**
 * `/banking/reconciliation` — per-account list of reconciliations and a
 * "New reconciliation" modal that immediately redirects to the board.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { BankAccountPicker } from "@/components/banking/BankAccountPicker";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type Recon = components["schemas"]["BankReconciliationResponse"];
type ReconCreate = components["schemas"]["BankReconciliationCreate"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

export function ReconciliationsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;
  const navigate = useNavigate();

  const [params, setParams] = useSearchParams();
  const accountId = params.get("account_id") ?? "";

  function setAccount(id: string) {
    const next = new URLSearchParams(params);
    if (id) next.set("account_id", id);
    else next.delete("account_id");
    setParams(next, { replace: true });
  }

  const [items, setItems] = useState<Recon[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  // New reconciliation form state
  const [modalAccount, setModalAccount] = useState("");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [stmtBalance, setStmtBalance] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/api/v1/bank-reconciliations", {
        params: accountId ? { account_id: accountId } : {},
      });
      setItems(res.data.items);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to load.");
    } finally {
      setLoading(false);
    }
  }, [accountId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function createRecon() {
    if (!modalAccount || !periodStart || !periodEnd || !stmtBalance) {
      setModalError("All fields are required.");
      return;
    }
    setSubmitting(true);
    setModalError(null);
    try {
      const body: ReconCreate = {
        account_id: modalAccount,
        period_start: periodStart,
        period_end: periodEnd,
        statement_ending_balance: stmtBalance,
      };
      const res = await apiClient.post<Recon>(
        "/api/v1/bank-reconciliations",
        body,
      );
      setModalOpen(false);
      navigate(`/banking/reconciliation/${res.data.id}`);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setModalError(typeof detail === "string" ? detail : "Could not create.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Reconciliations</h1>
        {canWrite ? (
          <Button
            onClick={() => setModalOpen(true)}
            data-testid="new-recon-btn"
          >
            New reconciliation
          </Button>
        ) : null}
      </header>

      <label className="block text-sm">
        Account
        <BankAccountPicker
          value={accountId}
          onChange={setAccount}
          data-testid="recon-account-filter"
        />
      </label>

      {error ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Period end</th>
            <th className="py-2 pr-2">State</th>
            <th className="py-2 pr-2 text-right">Statement</th>
            <th className="py-2 pr-2 text-right">Book</th>
            <th className="py-2 pr-2 text-right">Difference</th>
          </tr>
        </thead>
        <tbody>
          {loading && items.length === 0 ? (
            <tr>
              <td colSpan={5} className="py-4 text-center text-muted-foreground">
                Loading…
              </td>
            </tr>
          ) : items.length === 0 ? (
            <tr>
              <td colSpan={5} className="py-4 text-center text-muted-foreground">
                No reconciliations.
              </td>
            </tr>
          ) : (
            items.map((r) => (
              <tr
                key={r.id}
                className="border-b border-border/50"
                data-testid={`recon-row-${r.id}`}
              >
                <td className="py-2 pr-2">
                  <Link
                    to={`/banking/reconciliation/${r.id}`}
                    className="hover:underline"
                  >
                    {r.period_end}
                  </Link>
                </td>
                <td className="py-2 pr-2">{r.state}</td>
                <td className="py-2 pr-2 text-right font-mono">
                  {r.statement_ending_balance}
                </td>
                <td className="py-2 pr-2 text-right font-mono">
                  {r.book_ending_balance ?? "—"}
                </td>
                <td className="py-2 pr-2 text-right font-mono">
                  {r.difference ?? "—"}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent>
          <DialogTitle>New reconciliation</DialogTitle>
          <div className="mt-3 space-y-3 text-sm">
            <label className="block">
              Account
              <BankAccountPicker
                value={modalAccount}
                onChange={setModalAccount}
                data-testid="new-recon-account"
              />
            </label>
            <label className="block">
              Period start
              <Input
                type="date"
                value={periodStart}
                onChange={(e) => setPeriodStart(e.target.value)}
                data-testid="new-recon-start"
              />
            </label>
            <label className="block">
              Period end
              <Input
                type="date"
                value={periodEnd}
                onChange={(e) => setPeriodEnd(e.target.value)}
                data-testid="new-recon-end"
              />
            </label>
            <label className="block">
              Statement ending balance
              <Input
                type="number"
                step="0.01"
                value={stmtBalance}
                onChange={(e) => setStmtBalance(e.target.value)}
                data-testid="new-recon-balance"
              />
            </label>
            {modalError ? (
              <p role="alert" className="text-sm text-destructive">
                {modalError}
              </p>
            ) : null}
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => setModalOpen(false)}
                disabled={submitting}
              >
                Cancel
              </Button>
              <Button
                onClick={() => void createRecon()}
                disabled={submitting}
                data-testid="new-recon-submit"
              >
                {submitting ? "Creating…" : "Create"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}
