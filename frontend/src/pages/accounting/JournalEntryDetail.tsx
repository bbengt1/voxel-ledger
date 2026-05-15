/**
 * Journal entry detail. Shows header + lines; offers a Reverse action with
 * confirmation. Reversals are gated by role and by the entry's own state.
 */
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/Dialog";
import { useAuthStore } from "@/store/useAuthStore";

type JournalEntryResponse = components["schemas"]["JournalEntryResponse"];

const REVERSE_ROLES = new Set(["owner", "bookkeeper"]);

export function JournalEntryDetailPage() {
  const { id = "" } = useParams();
  const role = useAuthStore((s) => s.user?.role);
  const canReverse = !!role && REVERSE_ROLES.has(role);

  const [entry, setEntry] = useState<JournalEntryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    apiClient
      .get<JournalEntryResponse>(`/api/v1/accounting/entries/${id}`)
      .then((res) => {
        if (cancelled) return;
        setEntry(res.data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load entry.";
        setError(msg);
      });
    return () => {
      cancelled = true;
    };
  }, [id, reloadKey]);

  async function reverse() {
    if (!entry) return;
    setBusy(true);
    setError(null);
    try {
      await apiClient.post(
        `/api/v1/accounting/entries/${entry.id}/reverse`,
        { description: reason.trim() || null },
      );
      setConfirm(false);
      setReloadKey((k) => k + 1);
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Reverse failed.";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  if (!entry) {
    return (
      <section className="text-sm text-muted-foreground">
        {error ?? "Loading…"}
      </section>
    );
  }

  const isReversal = !!entry.reversal_of_entry_id;
  const reverseDisabled = entry.is_reversed || isReversal || !canReverse;
  const totalDebits = entry.lines
    .reduce((s, ln) => s + Number(ln.debit || 0), 0)
    .toFixed(2);
  const totalCredits = entry.lines
    .reduce((s, ln) => s + Number(ln.credit || 0), 0)
    .toFixed(2);

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">
            Entry{" "}
            <span className="font-mono text-base">{entry.entry_number}</span>
          </h1>
          <p className="text-xs text-muted-foreground">
            Posted {new Date(entry.posted_at).toLocaleString()}
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <Link to="/accounting/entries">Back</Link>
          </Button>
          <Button
            variant="destructive"
            onClick={() => setConfirm(true)}
            disabled={reverseDisabled}
            title={
              isReversal
                ? "Cannot reverse a reversal"
                : entry.is_reversed
                  ? "Already reversed"
                  : !canReverse
                    ? "Requires owner or bookkeeper"
                    : ""
            }
            data-testid="reverse-entry"
          >
            Reverse
          </Button>
        </div>
      </header>

      {error ? (
        <div role="alert" data-testid="detail-error" className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <p className="text-xs uppercase text-muted-foreground">Description</p>
          <p className="text-sm">{entry.description}</p>
        </div>
        <div>
          <p className="text-xs uppercase text-muted-foreground">Status</p>
          <p className="text-sm">
            {entry.is_reversed ? (
              <span className="rounded bg-muted px-1.5 py-0.5">Reversed</span>
            ) : isReversal ? (
              <span className="rounded bg-muted px-1.5 py-0.5">
                Reversal of{" "}
                <Link
                  to={`/accounting/entries/${entry.reversal_of_entry_id}`}
                  className="underline"
                  data-testid="reversal-of-link"
                >
                  prior entry
                </Link>
              </span>
            ) : (
              "Active"
            )}
          </p>
        </div>
      </div>

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Account</th>
            <th className="py-2 pr-2 text-right">Debit</th>
            <th className="py-2 pr-2 text-right">Credit</th>
            <th className="py-2 pr-2">Memo</th>
            <th className="py-2 pr-2">Division</th>
          </tr>
        </thead>
        <tbody>
          {entry.lines.map((ln) => (
            <tr key={ln.id} className="border-b border-border/40">
              <td className="py-1.5 pr-2">
                <span className="font-mono text-xs">{ln.account_code}</span>{" "}
                {ln.account_name}
              </td>
              <td className="py-1.5 pr-2 text-right tabular-nums">
                {Number(ln.debit) > 0 ? Number(ln.debit).toFixed(2) : ""}
              </td>
              <td className="py-1.5 pr-2 text-right tabular-nums">
                {Number(ln.credit) > 0 ? Number(ln.credit).toFixed(2) : ""}
              </td>
              <td className="py-1.5 pr-2 text-xs">{ln.memo ?? ""}</td>
              <td className="py-1.5 pr-2 text-xs">
                {ln.division_id ? ln.division_id.slice(0, 8) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-border text-sm font-semibold">
            <td className="py-2 pr-2">Totals</td>
            <td className="py-2 pr-2 text-right tabular-nums">{totalDebits}</td>
            <td className="py-2 pr-2 text-right tabular-nums">
              {totalCredits}
            </td>
            <td colSpan={2}></td>
          </tr>
        </tfoot>
      </table>

      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent data-testid="reverse-dialog">
          <DialogTitle>Reverse entry?</DialogTitle>
          <p className="mt-2 text-sm text-muted-foreground">
            Posts a counter-entry with mirrored debits and credits. The original
            entry is marked reversed and can't be reversed again.
          </p>
          <label className="mt-3 flex flex-col gap-1 text-xs">
            Reason (optional)
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="rounded-md border border-input bg-background p-2 text-sm"
              data-testid="reverse-reason"
            />
          </label>
          <div className="mt-4 flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => setConfirm(false)}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={reverse}
              disabled={busy}
              data-testid="confirm-reverse"
            >
              Reverse
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}
