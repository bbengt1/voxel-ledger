import { useCallback, useEffect, useState } from "react";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";

type AccountMap = components["schemas"]["AccountMapResponse"];
type QboAccount = components["schemas"]["QboAccountChoice"];

function humanizeRole(role: string): string {
  return role
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/**
 * Editor for the QBO posting-line role → account map (#315). Each role gets a
 * dropdown of the connected company's QBO accounts; saving persists the map
 * that Phase-3 postings resolve against.
 */
export function AccountMapEditor() {
  const [map, setMap] = useState<AccountMap | null>(null);
  const [accounts, setAccounts] = useState<QboAccount[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accountsError, setAccountsError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const mapRes = await api.get("/api/v1/admin/quickbooks/account-map");
      setMap(mapRes.data);
      const initial: Record<string, string> = {};
      for (const [role, entry] of Object.entries(mapRes.data.mappings)) {
        initial[role] = entry.qbo_account_id;
      }
      setDrafts(initial);
    } catch {
      setError("Failed to load the account map.");
    } finally {
      setLoading(false);
    }
    // Accounts come from a live QBO call — tolerate failure independently.
    try {
      const acctRes = await api.get("/api/v1/admin/quickbooks/accounts");
      setAccounts(acctRes.data);
      setAccountsError(null);
    } catch {
      setAccountsError(
        "Could not load QBO accounts (check the connection). You can still review the current map.",
      );
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const mappings: Record<string, { qbo_account_id: string; qbo_account_name: string | null }> =
        {};
      for (const [role, accountId] of Object.entries(drafts)) {
        if (!accountId) continue;
        const acct = accounts.find((a) => a.id === accountId);
        mappings[role] = { qbo_account_id: accountId, qbo_account_name: acct?.name ?? null };
      }
      const res = await api.put("/api/v1/admin/quickbooks/account-map", { mappings });
      setMap(res.data);
    } catch {
      setError("Failed to save the account map.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p className="text-sm text-muted-foreground">Loading account map…</p>;
  if (!map) return null;

  return (
    <section className="flex flex-col gap-3 border-t pt-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium">Account mapping</h3>
          <p className="text-xs text-muted-foreground">
            Map each posting role to a QuickBooks account. Required before transactions sync
            (Phase 3). {map.unmapped.length} of {map.roles.length} still unmapped.
          </p>
        </div>
        <Button onClick={save} disabled={saving || accounts.length === 0}>
          {saving ? "Saving…" : "Save mapping"}
        </Button>
      </div>

      {error ? (
        <div role="alert" className="rounded border border-destructive bg-destructive/10 p-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}
      {accountsError ? (
        <div className="rounded border border-amber-500 bg-amber-50 p-2 text-xs text-amber-800">
          {accountsError}
        </div>
      ) : null}

      <div className="overflow-x-auto">
        <table className="w-full min-w-[480px] text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="py-1 pr-4">Role</th>
              <th className="py-1">QuickBooks account</th>
            </tr>
          </thead>
          <tbody>
            {map.roles.map((role) => {
              const mapped = Boolean(drafts[role]);
              return (
                <tr key={role} className="border-b last:border-0">
                  <td className="py-1 pr-4">
                    {humanizeRole(role)}
                    {!mapped ? (
                      <span className="ml-2 text-xs text-amber-600">unmapped</span>
                    ) : null}
                  </td>
                  <td className="py-1">
                    <select
                      className="h-8 w-full rounded-md border border-input bg-background px-2 text-sm"
                      value={drafts[role] ?? ""}
                      disabled={accounts.length === 0}
                      onChange={(e) =>
                        setDrafts((prev) => ({ ...prev, [role]: e.target.value }))
                      }
                    >
                      <option value="">— unmapped —</option>
                      {accounts.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.name}
                          {a.account_type ? ` (${a.account_type})` : ""}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
