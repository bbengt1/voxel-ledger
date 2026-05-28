/**
 * Chart-of-accounts UI — two-pane: collapsible tree on the left, detail
 * (with inline edit, archive, balance) on the right.
 */
import { useEffect, useMemo, useState } from "react";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { NewAccountDialog } from "@/components/accounting/NewAccountDialog";
import {
  AccountTree,
  type AccountTreeNode,
  allIds,
  filterTree,
  flatten,
} from "@/components/accounting/AccountTree";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type AccountType = AccountTreeNode["type"];
type AccountResponse = components["schemas"]["AccountResponse"];
type AccountBalanceResponse =
  components["schemas"]["AccountBalanceResponse"];

const TYPE_OPTIONS: ReadonlyArray<{ value: AccountType | ""; label: string }> = [
  { value: "", label: "All types" },
  { value: "asset", label: "Asset" },
  { value: "liability", label: "Liability" },
  { value: "equity", label: "Equity" },
  { value: "revenue", label: "Revenue" },
  { value: "expense", label: "Expense" },
];

const WRITE_ROLES = new Set(["owner", "bookkeeper"]);
const OWNER_ROLES = new Set(["owner"]);

/**
 * The natural-sign convention: asset + expense are debit-normal (positive
 * shown as-is); liability, equity, revenue are credit-normal (we flip the
 * sign on the raw debit-minus-credit balance for display).
 */
function naturalBalance(type: AccountType, raw: string): string {
  const n = Number(raw);
  if (Number.isNaN(n)) return raw;
  if (type === "asset" || type === "expense") return n.toFixed(2);
  return (-n).toFixed(2);
}

export function AccountsTreePage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = !!role && WRITE_ROLES.has(role);
  const canArchive = !!role && OWNER_ROLES.has(role);

  const [tree, setTree] = useState<AccountTreeNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<AccountType | "">("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AccountResponse | null>(null);
  const [balance, setBalance] = useState<AccountBalanceResponse | null>(null);
  const [editing, setEditing] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftDescription, setDraftDescription] = useState("");
  const [draftParentId, setDraftParentId] = useState<string>("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  // Load tree.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/accounts/tree")
      .then((res) => {
        if (cancelled) return;
        setTree(res.data.items);
        // Auto-expand top-level.
        setExpanded((prev) => {
          if (prev.size > 0) return prev;
          return new Set(res.data.items.map((n) => n.id));
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load accounts.";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  // Load detail + balance when selectedId changes.
  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setBalance(null);
      return;
    }
    let cancelled = false;
    setActionError(null);
    apiClient
      .get<AccountResponse>(`/api/v1/accounts/${selectedId}`)
      .then((res) => {
        if (cancelled) return;
        setDetail(res.data);
        setDraftName(res.data.name);
        setDraftDescription(res.data.description ?? "");
        setDraftParentId(res.data.parent_account_id ?? "");
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      });
    api
      .get("/api/v1/accounting/account-balances", {
        params: { account_id: selectedId },
      })
      .then((res) => {
        if (cancelled) return;
        setBalance(res.data.items[0] ?? null);
      })
      .catch(() => {
        if (!cancelled) setBalance(null);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, reloadKey]);

  const filtered = useMemo(
    () => filterTree(tree, typeFilter, includeArchived),
    [tree, typeFilter, includeArchived],
  );

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function expandAll() {
    setExpanded(allIds(filtered));
  }
  function collapseAll() {
    setExpanded(new Set());
  }

  const allAccounts = useMemo(() => flatten(tree), [tree]);

  async function saveEdit() {
    if (!detail) return;
    setBusy(true);
    setActionError(null);
    try {
      await apiClient.patch(`/api/v1/accounts/${detail.id}`, {
        name: draftName,
        description: draftDescription || null,
        parent_account_id: draftParentId || null,
      });
      setEditing(false);
      setReloadKey((k) => k + 1);
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Update failed.";
      setActionError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function archive() {
    if (!detail) return;
    setBusy(true);
    setActionError(null);
    try {
      await apiClient.post(`/api/v1/accounts/${detail.id}/archive`, {});
      setArchiveOpen(false);
      setReloadKey((k) => k + 1);
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Archive failed.";
      setActionError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Chart of accounts</h1>
        {canWrite ? (
          <Button onClick={() => setNewOpen(true)} data-testid="open-new-account">
            New account
          </Button>
        ) : null}
      </header>

      {error ? (
        <div
          role="alert"
          data-testid="accounts-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[320px_1fr]">
        <div className="rounded-md border border-border bg-muted/20 p-3">
          <div className="flex flex-col gap-2">
            <label className="flex flex-col gap-1 text-xs font-medium">
              Type
              <select
                className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                value={typeFilter}
                onChange={(e) =>
                  setTypeFilter(e.target.value as AccountType | "")
                }
                data-testid="filter-type"
              >
                {TYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={includeArchived}
                onChange={(e) => setIncludeArchived(e.target.checked)}
                data-testid="filter-archived"
              />
              Show archived
            </label>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={expandAll}
                data-testid="expand-all"
              >
                Expand all
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={collapseAll}
                data-testid="collapse-all"
              >
                Collapse all
              </Button>
            </div>
          </div>
          <hr className="my-3 border-border" />
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (
            <AccountTree
              nodes={filtered}
              selectedId={selectedId}
              expanded={expanded}
              onToggle={toggle}
              onSelect={(id) => {
                setSelectedId(id);
                setEditing(false);
              }}
            />
          )}
        </div>

        <div className="rounded-md border border-border p-4">
          {!detail ? (
            <p className="text-sm text-muted-foreground">
              Select an account to see details.
            </p>
          ) : (
            <div className="flex flex-col gap-3 text-sm">
              <header className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-lg font-semibold">
                    <span className="font-mono text-sm text-muted-foreground">
                      {detail.code}
                    </span>{" "}
                    {detail.name}
                    {detail.is_archived ? (
                      <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs uppercase text-muted-foreground">
                        archived
                      </span>
                    ) : null}
                  </h2>
                  <p className="text-xs text-muted-foreground">
                    Type: <strong>{detail.type}</strong>
                  </p>
                </div>
                <div className="flex gap-2">
                  {canWrite && !editing && !detail.is_archived ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setEditing(true)}
                      data-testid="edit-account"
                    >
                      Edit
                    </Button>
                  ) : null}
                  {canArchive && !detail.is_archived ? (
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => setArchiveOpen(true)}
                      data-testid="archive-account"
                    >
                      Archive
                    </Button>
                  ) : null}
                </div>
              </header>

              {actionError ? (
                <div
                  role="alert"
                  data-testid="detail-error"
                  className="rounded border border-destructive bg-destructive/10 p-2 text-xs text-destructive"
                >
                  {actionError}
                </div>
              ) : null}

              {detail.parent_chain && detail.parent_chain.length > 0 ? (
                <div className="text-xs text-muted-foreground">
                  Parent chain:{" "}
                  {detail.parent_chain.map((p, i) => (
                    <span key={p.id}>
                      {i > 0 ? " › " : ""}
                      <button
                        type="button"
                        className="hover:underline"
                        onClick={() => setSelectedId(p.id)}
                      >
                        {p.code} {p.name}
                      </button>
                    </span>
                  ))}
                </div>
              ) : null}

              {editing ? (
                <div className="flex flex-col gap-2">
                  <label className="flex flex-col gap-1 text-xs">
                    Name
                    <Input
                      value={draftName}
                      onChange={(e) => setDraftName(e.target.value)}
                      data-testid="edit-name"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs">
                    Description
                    <textarea
                      className="rounded-md border border-input bg-background p-2 text-sm"
                      value={draftDescription}
                      onChange={(e) => setDraftDescription(e.target.value)}
                      data-testid="edit-description"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs">
                    Parent
                    <select
                      className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                      value={draftParentId}
                      onChange={(e) => setDraftParentId(e.target.value)}
                      data-testid="edit-parent"
                    >
                      <option value="">(top-level)</option>
                      {allAccounts
                        .filter(
                          (a) => a.id !== detail.id && a.type === detail.type,
                        )
                        .map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.code} — {a.name}
                          </option>
                        ))}
                    </select>
                  </label>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      onClick={saveEdit}
                      disabled={busy || !draftName.trim()}
                      data-testid="save-edit"
                    >
                      Save
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setEditing(false)}
                      disabled={busy}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <>
                  {detail.description ? (
                    <p className="text-sm">{detail.description}</p>
                  ) : null}
                </>
              )}

              <div className="rounded border border-border bg-muted/20 p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">
                  Balance
                </p>
                <p
                  className="text-2xl tabular-nums"
                  data-testid="account-balance"
                >
                  {balance
                    ? naturalBalance(detail.type, balance.balance)
                    : "—"}
                </p>
                {balance ? (
                  <p className="text-xs text-muted-foreground">
                    Debits {balance.total_debits} / credits{" "}
                    {balance.total_credits}
                  </p>
                ) : null}
              </div>
            </div>
          )}
        </div>
      </div>

      <NewAccountDialog
        open={newOpen}
        onClose={() => setNewOpen(false)}
        onCreated={() => {
          setNewOpen(false);
          setReloadKey((k) => k + 1);
        }}
        seedParentId={selectedId ?? undefined}
      />

      <Dialog open={archiveOpen} onOpenChange={setArchiveOpen}>
        <DialogContent data-testid="archive-dialog">
          <DialogTitle>Archive account?</DialogTitle>
          <p className="mt-2 text-sm text-muted-foreground">
            Archiving hides the account from pickers and the default tree.
            Existing journal entries are unaffected.
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => setArchiveOpen(false)}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={archive}
              disabled={busy}
              data-testid="confirm-archive"
            >
              Archive
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}

