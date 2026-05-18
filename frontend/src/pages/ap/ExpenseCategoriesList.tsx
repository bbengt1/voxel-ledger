/**
 * `/expense-categories` — flat list of expense categories with code,
 * name, default-expense-account, parent badge, and an active toggle.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiClient } from "@/api/client";
import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
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

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Expense categories</h1>
        {canWrite ? (
          <Button asChild>
            <Link to="/expense-categories/new">New category</Link>
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
            <th className="py-2 pr-2">Code</th>
            <th className="py-2 pr-2">Name</th>
            <th className="py-2 pr-2">Parent</th>
            <th className="py-2 pr-2">Active</th>
            <th className="py-2 pr-2"></th>
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
                No categories yet.
              </td>
            </tr>
          ) : (
            items.map((c) => (
              <tr
                key={c.id}
                className="border-b border-border/50 hover:bg-accent/30"
                data-testid={`category-row-${c.id}`}
              >
                <td className="py-2 pr-2 font-mono text-xs">
                  <Link
                    to={`/expense-categories/${c.id}`}
                    className="hover:underline"
                  >
                    {c.code}
                  </Link>
                </td>
                <td className="py-2 pr-2">{c.name}</td>
                <td className="py-2 pr-2 font-mono text-xs">
                  {c.parent_id ? (
                    <span className="rounded border border-border px-1">
                      {c.parent_id.slice(0, 8)}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="py-2 pr-2">{c.is_active ? "yes" : "no"}</td>
                <td className="py-2 pr-2 text-right">
                  {canWrite ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void toggleActive(c)}
                      data-testid={`toggle-active-${c.id}`}
                    >
                      {c.is_active ? "Archive" : "Activate"}
                    </Button>
                  ) : null}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}
