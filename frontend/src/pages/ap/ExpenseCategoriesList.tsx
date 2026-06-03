/**
 * `/expense-categories` — flat list of expense categories with code,
 * name, default-expense-account, parent badge, and an active toggle.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { useAuthStore } from "@/store/useAuthStore";

type ExpenseCategoryResponse = components["schemas"]["ExpenseCategoryResponse"];

const CAN_WRITE: readonly string[] = ["owner", "bookkeeper"];

export function ExpenseCategoriesListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const canWrite = role ? CAN_WRITE.includes(role) : false;

  const [items, setItems] = useState<ExpenseCategoryResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get("/api/v1/expense-categories")
      .then((res) => {
        if (!cancelled) setItems(res.data.items);
      })
      .catch(() => {
        if (!cancelled) setError("Failed to load expense categories.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const teardown = refetch();
    return () => teardown();
  }, [refetch]);

  async function toggleActive(c: ExpenseCategoryResponse) {
    try {
      if (c.is_active) {
        await apiClient.post(`/api/v1/expense-categories/${c.id}/archive`);
      } else {
        await apiClient.patch(`/api/v1/expense-categories/${c.id}`, {
          is_active: true,
        });
      }
      refetch();
    } catch {
      setError("Could not change active state.");
    }
  }

  const columns: DataTableColumn<ExpenseCategoryResponse>[] = [
    {
      key: "code",
      header: "Code",
      isPrimary: true,
      cell: (c) => (
        <Link
          to={`/expense-categories/${c.id}`}
          className="font-mono text-xs hover:underline"
        >
          {c.code}
        </Link>
      ),
    },
    { key: "name", header: "Name", cell: (c) => c.name },
    {
      key: "parent",
      header: "Parent",
      cell: (c) =>
        c.parent_id ? (
          <span className="rounded border border-border px-1 font-mono text-xs">
            {c.parent_id.slice(0, 8)}
          </span>
        ) : (
          "—"
        ),
    },
    { key: "active", header: "Active", cell: (c) => (c.is_active ? "yes" : "no") },
    {
      key: "actions",
      header: "",
      align: "right",
      cardFullWidth: true,
      cell: (c) =>
        canWrite ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => void toggleActive(c)}
            data-testid={`toggle-active-${c.id}`}
          >
            {c.is_active ? "Archive" : "Activate"}
          </Button>
        ) : null,
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Expense categories"
        actions={
          canWrite ? (
            <Button asChild>
              <Link to="/expense-categories/new">New category</Link>
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
        getRowKey={(c) => c.id}
        loading={loading && items.length === 0}
        emptyMessage="No categories yet."
        minWidthClassName="min-w-[640px]"
        rowClassName={() => "hover:bg-accent/30"}
      />
    </section>
  );
}
