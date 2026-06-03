/**
 * Editable line grid for journal-entry composition.
 *
 * Maintains debit/credit mutual exclusion per line, sums totals, and
 * reports lines + balance state up to the parent.
 */
import { useEffect, useState } from "react";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import {
  AccountPicker,
  type AccountOption,
} from "@/components/accounting/AccountPicker";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

type DivisionResponse = components["schemas"]["DivisionResponse"];

export interface JournalLineDraft {
  /** Stable key for React; not sent to backend. */
  key: string;
  account: AccountOption | null;
  debit: string;
  credit: string;
  memo: string;
  divisionId: string;
}

interface Props {
  lines: JournalLineDraft[];
  onChange: (next: JournalLineDraft[]) => void;
}

function makeLine(): JournalLineDraft {
  return {
    key: crypto.randomUUID(),
    account: null,
    debit: "",
    credit: "",
    memo: "",
    divisionId: "",
  };
}

export function emptyLines(n = 2): JournalLineDraft[] {
  return Array.from({ length: n }, () => makeLine());
}

function dec(v: string): number {
  if (!v.trim()) return 0;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

export function lineTotals(lines: JournalLineDraft[]) {
  let totalDebits = 0;
  let totalCredits = 0;
  for (const ln of lines) {
    totalDebits += dec(ln.debit);
    totalCredits += dec(ln.credit);
  }
  const difference = totalDebits - totalCredits;
  return { totalDebits, totalCredits, difference };
}

export function isReadyToSubmit(lines: JournalLineDraft[]): boolean {
  if (lines.length < 2) return false;
  for (const ln of lines) {
    if (!ln.account) return false;
    const d = dec(ln.debit);
    const c = dec(ln.credit);
    if (!((d > 0 && c === 0) || (c > 0 && d === 0))) return false;
  }
  const { difference } = lineTotals(lines);
  return Math.abs(difference) < 1e-9;
}

export function JournalLineGrid({ lines, onChange }: Props) {
  const [divisions, setDivisions] = useState<DivisionResponse[]>([]);

  useEffect(() => {
    let cancelled = false;
    api
      .get("/api/v1/accounting/divisions", {
        params: { is_archived: "false" },
      })
      .then((res) => {
        if (cancelled) return;
        setDivisions(res.data.items);
      })
      .catch(() => {
        if (!cancelled) setDivisions([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function update(idx: number, patch: Partial<JournalLineDraft>) {
    const next = lines.slice();
    next[idx] = { ...next[idx]!, ...patch };
    onChange(next);
  }

  function addRow() {
    onChange([...lines, makeLine()]);
  }

  function removeRow(idx: number) {
    if (lines.length <= 2) return;
    const next = lines.slice();
    next.splice(idx, 1);
    onChange(next);
  }

  const { totalDebits, totalCredits, difference } = lineTotals(lines);
  const balanced = Math.abs(difference) < 1e-9;

  return (
    <div className="flex flex-col gap-2" data-testid="line-grid">
      <div className="overflow-x-auto">
      <table className="w-full min-w-[48rem] border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2 w-[34%]">Account</th>
            <th className="py-2 pr-2 text-right">Debit</th>
            <th className="py-2 pr-2 text-right">Credit</th>
            <th className="py-2 pr-2">Memo</th>
            <th className="py-2 pr-2">Division</th>
            <th className="py-2"></th>
          </tr>
        </thead>
        <tbody>
          {lines.map((ln, idx) => (
            <tr key={ln.key} className="border-b border-border/40 align-top">
              <td className="py-1 pr-2">
                <AccountPicker
                  value={ln.account}
                  onChange={(opt) => update(idx, { account: opt })}
                  data-testid={`line-${idx}-account`}
                />
              </td>
              <td className="py-1 pr-2">
                <Input
                  inputMode="decimal"
                  value={ln.debit}
                  onChange={(e) =>
                    update(idx, {
                      debit: e.target.value,
                      credit: e.target.value ? "" : ln.credit,
                    })
                  }
                  className="text-right tabular-nums"
                  data-testid={`line-${idx}-debit`}
                />
              </td>
              <td className="py-1 pr-2">
                <Input
                  inputMode="decimal"
                  value={ln.credit}
                  onChange={(e) =>
                    update(idx, {
                      credit: e.target.value,
                      debit: e.target.value ? "" : ln.debit,
                    })
                  }
                  className="text-right tabular-nums"
                  data-testid={`line-${idx}-credit`}
                />
              </td>
              <td className="py-1 pr-2">
                <Input
                  value={ln.memo}
                  onChange={(e) => update(idx, { memo: e.target.value })}
                  data-testid={`line-${idx}-memo`}
                />
              </td>
              <td className="py-1 pr-2">
                <select
                  className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                  value={ln.divisionId}
                  onChange={(e) =>
                    update(idx, { divisionId: e.target.value })
                  }
                  data-testid={`line-${idx}-division`}
                >
                  <option value="">(none)</option>
                  {divisions.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.code} — {d.name}
                    </option>
                  ))}
                </select>
              </td>
              <td className="py-1">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeRow(idx)}
                  disabled={lines.length <= 2}
                  data-testid={`line-${idx}-remove`}
                >
                  ×
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <div className="flex items-center justify-between">
        <Button
          size="sm"
          variant="outline"
          onClick={addRow}
          data-testid="add-row"
        >
          Add row
        </Button>
        <dl
          className="flex items-center gap-4 text-sm tabular-nums"
          data-testid="line-totals"
        >
          <div>
            <dt className="inline text-xs uppercase text-muted-foreground">
              Total debits{" "}
            </dt>
            <dd className="inline font-medium" data-testid="total-debits">
              {totalDebits.toFixed(2)}
            </dd>
          </div>
          <div>
            <dt className="inline text-xs uppercase text-muted-foreground">
              Total credits{" "}
            </dt>
            <dd className="inline font-medium" data-testid="total-credits">
              {totalCredits.toFixed(2)}
            </dd>
          </div>
          <div>
            <dt className="inline text-xs uppercase text-muted-foreground">
              Difference{" "}
            </dt>
            <dd
              className={
                "inline font-semibold " +
                (balanced ? "text-emerald-600" : "text-destructive")
              }
              data-testid="difference"
            >
              {difference.toFixed(2)}
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
