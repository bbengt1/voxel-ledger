/**
 * Type-aware payload renderer for ``accounting.large_journal_entry``
 * approval requests.
 *
 * Reads each line's account on demand for code+name display. Falls back to
 * a short id slice if the lookup fails.
 */
import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";

type AccountResponse = components["schemas"]["AccountResponse"];

export interface JournalLinePayload {
  account_id: string;
  debit: string | number;
  credit: string | number;
  memo?: string | null;
  division_id?: string | null;
  line_number?: number;
}

export interface JournalEntryPayload {
  description?: string;
  posted_at?: string;
  lines?: JournalLinePayload[];
}

interface Props {
  payload: JournalEntryPayload;
}

export function JournalEntryPayloadRenderer({ payload }: Props) {
  const lines = payload.lines ?? [];
  const [accounts, setAccounts] = useState<Map<string, AccountResponse>>(
    new Map(),
  );

  useEffect(() => {
    const ids = Array.from(
      new Set(lines.map((ln) => ln.account_id).filter(Boolean)),
    );
    if (ids.length === 0) return;
    let cancelled = false;
    Promise.all(
      ids.map((id) =>
        apiClient
          .get<AccountResponse>(`/api/v1/accounts/${id}`)
          .then((res) => [id, res.data] as const)
          .catch(() => [id, null] as const),
      ),
    ).then((pairs) => {
      if (cancelled) return;
      setAccounts((prev) => {
        const next = new Map(prev);
        for (const [id, acc] of pairs) {
          if (acc) next.set(id, acc);
        }
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(lines.map((l) => l.account_id))]);

  const totalDebits = lines
    .reduce((s, ln) => s + Number(ln.debit || 0), 0)
    .toFixed(2);
  const totalCredits = lines
    .reduce((s, ln) => s + Number(ln.credit || 0), 0)
    .toFixed(2);

  return (
    <div className="flex flex-col gap-3 text-sm" data-testid="payload-journal-entry">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <div>
          <p className="text-xs uppercase text-muted-foreground">Description</p>
          <p>{payload.description ?? "—"}</p>
        </div>
        <div>
          <p className="text-xs uppercase text-muted-foreground">Posted at</p>
          <p>
            {payload.posted_at
              ? new Date(payload.posted_at).toLocaleString()
              : "—"}
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
          </tr>
        </thead>
        <tbody>
          {lines.map((ln, idx) => {
            const acc = accounts.get(ln.account_id);
            return (
              <tr key={idx} className="border-b border-border/40">
                <td className="py-1.5 pr-2">
                  {acc ? (
                    <>
                      <span className="font-mono text-xs">{acc.code}</span>{" "}
                      {acc.name}
                    </>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      {ln.account_id.slice(0, 8)}…
                    </span>
                  )}
                </td>
                <td className="py-1.5 pr-2 text-right tabular-nums">
                  {Number(ln.debit) > 0 ? Number(ln.debit).toFixed(2) : ""}
                </td>
                <td className="py-1.5 pr-2 text-right tabular-nums">
                  {Number(ln.credit) > 0 ? Number(ln.credit).toFixed(2) : ""}
                </td>
                <td className="py-1.5 pr-2 text-xs">{ln.memo ?? ""}</td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr className="border-t border-border text-sm font-semibold">
            <td className="py-2 pr-2">Totals</td>
            <td className="py-2 pr-2 text-right tabular-nums">{totalDebits}</td>
            <td className="py-2 pr-2 text-right tabular-nums">{totalCredits}</td>
            <td></td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
