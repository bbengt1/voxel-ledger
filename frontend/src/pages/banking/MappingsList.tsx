/**
 * `/banking/mappings` — saved bank-statement import mappings.
 * Lists per-account CSV/OFX mappings with a deactivate action.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, apiClient } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
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

  const columns: DataTableColumn<Mapping>[] = [
    {
      key: "name",
      header: "Name",
      isPrimary: true,
      cell: (m) => <span className="font-medium">{m.name}</span>,
    },
    {
      key: "account",
      header: "Account",
      cell: (m) => {
        const acct = accounts[m.account_id];
        return acct ? `${acct.code} · ${acct.name}` : m.account_id;
      },
    },
    {
      key: "file_kind",
      header: "File kind",
      cell: (m) => <span className="uppercase">{m.file_kind}</span>,
    },
    {
      key: "is_active",
      header: "Active",
      cell: (m) => (m.is_active ? "yes" : "no"),
    },
    {
      key: "actions",
      header: "Actions",
      align: "right",
      cardFullWidth: true,
      cell: (m) =>
        canWrite && m.is_active ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => void deactivate(m.id)}
            data-testid={`deactivate-${m.id}`}
          >
            Deactivate
          </Button>
        ) : null,
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Bank import mappings"
        actions={
          canWrite ? (
            <Button asChild>
              <Link to="/banking/mappings/new">New mapping</Link>
            </Button>
          ) : null
        }
      />

      {error ? (
        <div
          role="alert"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(m) => m.id}
        loading={loading && items.length === 0}
        emptyMessage="No mappings yet."
        minWidthClassName="min-w-[640px]"
      />
    </section>
  );
}
