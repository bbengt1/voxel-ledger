/**
 * `/banking/mappings` — saved bank-statement import mappings.
 * Lists per-account CSV/OFX mappings with a deactivate action.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, apiClient } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/store/useAuthStore";

type Mapping = components["schemas"]["BankImportMappingResponse"];
type Account = components["schemas"]["AccountResponse"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

export function MappingsListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [items, setItems] = useState<Mapping[]>([]);
  const [accounts, setAccounts] = useState<Record<string, Account>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [mappingsRes, accountsRes] = await Promise.all([
        api.get("/api/v1/bank-import-mappings"),
        api.get("/api/v1/accounts"),
      ]);
      setItems(mappingsRes.data.items);
      const acctMap: Record<string, Account> = {};
      const acctItems = (accountsRes.data as { items: Account[] }).items ?? [];
      for (const a of acctItems) acctMap[a.id] = a;
      setAccounts(acctMap);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Failed to load mappings.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function deactivate(id: string) {
    try {
      await apiClient.post(`/api/v1/bank-import-mappings/${id}/deactivate`);
      await load();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : "Failed to deactivate mapping.",
      );
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Bank import mappings</h1>
        {canWrite ? (
          <Button asChild>
            <Link to="/banking/mappings/new">New mapping</Link>
          </Button>
        ) : null}
      </header>

      {error ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Name</th>
            <th className="py-2 pr-2">Account</th>
            <th className="py-2 pr-2">File kind</th>
            <th className="py-2 pr-2">Active</th>
            <th className="py-2 pr-2 text-right">Actions</th>
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
                No mappings yet.
              </td>
            </tr>
          ) : (
            items.map((m) => {
              const acct = accounts[m.account_id];
              return (
                <tr
                  key={m.id}
                  className="border-b border-border/50"
                  data-testid={`mapping-row-${m.id}`}
                >
                  <td className="py-2 pr-2 font-medium">{m.name}</td>
                  <td className="py-2 pr-2">
                    {acct ? `${acct.code} · ${acct.name}` : m.account_id}
                  </td>
                  <td className="py-2 pr-2 uppercase">{m.file_kind}</td>
                  <td className="py-2 pr-2">{m.is_active ? "yes" : "no"}</td>
                  <td className="py-2 pr-2 text-right">
                    {canWrite && m.is_active ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void deactivate(m.id)}
                        data-testid={`deactivate-${m.id}`}
                      >
                        Deactivate
                      </Button>
                    ) : null}
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
