/**
 * Accounting periods list with state-machine action buttons.
 */
import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PeriodStateActions } from "@/components/accounting/PeriodStateActions";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type AccountingPeriodResponse =
  components["schemas"]["AccountingPeriodResponse"];

const STATE_COLOR: Record<AccountingPeriodResponse["state"], string> = {
  open: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200",
  closed: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200",
  locked: "bg-muted text-muted-foreground",
};

const WRITE_ROLES = new Set(["owner", "bookkeeper"]);

interface ActorLite {
  email: string;
}

export function PeriodsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canCreate = !!role && WRITE_ROLES.has(role);

  const [items, setItems] = useState<AccountingPeriodResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [actors, setActors] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    let cancelled = false;
    setError(null);
    api
      .get("/api/v1/accounting/periods")
      .then((res) => {
        if (cancelled) return;
        setItems(res.data.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load periods.";
        setError(msg);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  // Resolve closed-by emails.
  useEffect(() => {
    const missing = Array.from(
      new Set(
        items
          .map((p) => p.closed_by_user_id)
          .filter((id): id is string => !!id && !actors.has(id)),
      ),
    );
    if (missing.length === 0) return;
    let cancelled = false;
    Promise.all(
      missing.map((id) =>
        apiClient
          .get<ActorLite>(`/api/v1/users/${id}`)
          .then((res) => [id, res.data.email] as const)
          .catch(() => [id, id.slice(0, 8)] as const),
      ),
    ).then((pairs) => {
      if (cancelled) return;
      setActors((prev) => {
        const next = new Map(prev);
        for (const [id, email] of pairs) next.set(id, email);
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [items, actors]);

  async function action(
    period: AccountingPeriodResponse,
    kind: "close" | "reopen" | "lock",
  ) {
    setBusy(true);
    setError(null);
    try {
      await apiClient.post(
        `/api/v1/accounting/periods/${period.id}/${kind}`,
        {},
      );
      setReloadKey((k) => k + 1);
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? `${kind} failed.`;
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Accounting periods</h1>
        {canCreate ? (
          <Button onClick={() => setNewOpen(true)} data-testid="open-new-period">
            New period
          </Button>
        ) : null}
      </header>

      {error ? (
        <div
          role="alert"
          data-testid="periods-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Name</th>
            <th className="py-2 pr-2">Start</th>
            <th className="py-2 pr-2">End</th>
            <th className="py-2 pr-2">State</th>
            <th className="py-2 pr-2">Closed</th>
            <th className="py-2 pr-2">Locked at</th>
            <th className="py-2 pr-2 text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <tr>
              <td colSpan={7} className="py-4 text-center text-muted-foreground">
                No periods yet.
              </td>
            </tr>
          ) : (
            items.map((p) => (
              <tr key={p.id} className="border-b border-border/50">
                <td className="py-2 pr-2">{p.name}</td>
                <td className="py-2 pr-2 text-xs">{p.start_date}</td>
                <td className="py-2 pr-2 text-xs">{p.end_date}</td>
                <td className="py-2 pr-2">
                  <span
                    className={
                      "rounded px-1.5 py-0.5 text-xs font-medium " +
                      STATE_COLOR[p.state]
                    }
                    data-testid={`state-${p.id}`}
                  >
                    {p.state}
                  </span>
                </td>
                <td className="py-2 pr-2 text-xs">
                  {p.closed_at ? (
                    <>
                      {new Date(p.closed_at).toLocaleDateString()}
                      {p.closed_by_user_id ? (
                        <>
                          {" "}
                          by{" "}
                          {actors.get(p.closed_by_user_id) ??
                            p.closed_by_user_id.slice(0, 8)}
                        </>
                      ) : null}
                    </>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="py-2 pr-2 text-xs">
                  {p.locked_at
                    ? new Date(p.locked_at).toLocaleDateString()
                    : "—"}
                </td>
                <td className="py-2 pr-2 text-right">
                  <PeriodStateActions
                    period={p}
                    role={role}
                    busy={busy}
                    onAction={action}
                  />
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      <NewPeriodDialog
        open={newOpen}
        onClose={() => setNewOpen(false)}
        onCreated={() => {
          setNewOpen(false);
          setReloadKey((k) => k + 1);
        }}
      />
    </section>
  );
}

function NewPeriodDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName("");
      setStartDate("");
      setEndDate("");
      setError(null);
    }
  }, [open]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await apiClient.post("/api/v1/accounting/periods", {
        name: name.trim(),
        start_date: startDate,
        end_date: endDate,
      });
      onCreated();
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Create failed.";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => (!v ? onClose() : undefined)}>
      <DialogContent data-testid="new-period-dialog">
        <DialogTitle>New accounting period</DialogTitle>
        <div className="mt-3 flex flex-col gap-2">
          {error ? (
            <div
              role="alert"
              data-testid="new-period-error"
              className="rounded border border-destructive bg-destructive/10 p-2 text-xs text-destructive"
            >
              {error}
            </div>
          ) : null}
          <label className="flex flex-col gap-1 text-xs">
            Name
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. 2026-Q1"
              data-testid="new-period-name"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            Start date
            <Input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              data-testid="new-period-start"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            End date
            <Input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              data-testid="new-period-end"
            />
          </label>
          <div className="mt-2 flex justify-end gap-2">
            <Button variant="outline" onClick={onClose} disabled={busy}>
              Cancel
            </Button>
            <Button
              onClick={submit}
              disabled={busy || !name.trim() || !startDate || !endDate}
              data-testid="submit-new-period"
            >
              Create
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
