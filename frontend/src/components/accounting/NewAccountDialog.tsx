/**
 * Reusable "create account" modal.
 *
 * Originally lived inline in :mod:`AccountsTree`; extracted so other
 * pages (e.g. the tax-profile composer) can launch the same flow
 * without a sessionStorage round-trip. The dialog self-fetches its
 * parent-account dropdown so callers don't have to pass a tree in.
 *
 * ``onCreated`` receives the freshly-created ``AccountResponse`` so the
 * caller can apply it (set a picker value, push it into a draft row,
 * etc.) without a separate refetch.
 */
import { useEffect, useState } from "react";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";

export type AccountType = "asset" | "liability" | "equity" | "revenue" | "expense";

type AccountResponse = components["schemas"]["AccountResponse"];

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (account: AccountResponse) => void;
  /** Pre-fill the Name field. */
  seedName?: string;
  /** Pre-select an account type. Locks the dropdown when a parent is
   * also seeded since type follows the parent. */
  seedType?: AccountType;
  /** Pre-select a parent account. */
  seedParentId?: string;
}

export function NewAccountDialog({
  open,
  onClose,
  onCreated,
  seedName,
  seedType,
  seedParentId,
}: Props) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [parentId, setParentId] = useState<string>("");
  const [type, setType] = useState<AccountType>(seedType ?? "asset");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [allAccounts, setAllAccounts] = useState<AccountResponse[]>([]);

  // Refresh inputs and load parent options each time the dialog opens
  // so a closed-and-reopened modal honors fresh seeds.
  useEffect(() => {
    if (!open) return;
    setCode("");
    setName(seedName ?? "");
    setDescription("");
    setError(null);
    setParentId(seedParentId ?? "");
    setType(seedType ?? "asset");
    api
      .get("/api/v1/accounts")
      .then((res) => {
        const items =
          (res.data as { items: AccountResponse[] }).items ?? [];
        setAllAccounts(items.filter((a) => !a.is_archived));
      })
      .catch(() => {
        /* non-fatal — parent dropdown just shows nothing */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // When a parent is chosen, the child inherits the parent's type.
  useEffect(() => {
    if (!parentId) return;
    const parent = allAccounts.find((a) => a.id === parentId);
    if (parent) setType(parent.type as AccountType);
  }, [parentId, allAccounts]);

  const typeLocked = !!parentId;

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const res = await apiClient.post<AccountResponse>("/api/v1/accounts", {
        code: code.trim(),
        name: name.trim(),
        type,
        description: description.trim() || null,
        parent_account_id: parentId || null,
      });
      onCreated(res.data);
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data
          ?.detail ?? "Create failed.";
      setError(typeof msg === "string" ? msg : "Create failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => (!v ? onClose() : undefined)}>
      <DialogContent data-testid="new-account-dialog">
        <DialogTitle>New account</DialogTitle>
        <div className="mt-3 flex flex-col gap-2">
          {error ? (
            <div
              role="alert"
              data-testid="new-account-error"
              className="rounded border border-destructive bg-destructive/10 p-2 text-xs text-destructive"
            >
              {error}
            </div>
          ) : null}
          <label className="flex flex-col gap-1 text-xs">
            Code
            <Input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              data-testid="new-code"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            Name
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              data-testid="new-name"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            Parent
            <select
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              value={parentId}
              onChange={(e) => setParentId(e.target.value)}
              data-testid="new-parent"
            >
              <option value="">(top-level)</option>
              {allAccounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.code} — {a.name} ({a.type})
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs">
            Type
            <select
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              value={type}
              onChange={(e) => setType(e.target.value as AccountType)}
              disabled={typeLocked}
              data-testid="new-type"
            >
              <option value="asset">Asset</option>
              <option value="liability">Liability</option>
              <option value="equity">Equity</option>
              <option value="revenue">Revenue</option>
              <option value="expense">Expense</option>
            </select>
            {typeLocked ? (
              <span className="text-[10px] text-muted-foreground">
                Type follows the parent.
              </span>
            ) : null}
          </label>
          <label className="flex flex-col gap-1 text-xs">
            Description
            <textarea
              className="rounded-md border border-input bg-background p-2 text-sm"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <div className="mt-2 flex justify-end gap-2">
            <Button variant="outline" onClick={onClose} disabled={busy}>
              Cancel
            </Button>
            <Button
              onClick={submit}
              disabled={busy || !code.trim() || !name.trim()}
              data-testid="submit-new-account"
            >
              Create
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
