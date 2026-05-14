import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/store/useAuthStore";

type UserResponse = components["schemas"]["UserResponse"];
type Role = components["schemas"]["Role"];

const ROLES: Role[] = ["owner", "bookkeeper", "production", "sales", "viewer"];

const DEBOUNCE_MS = 250;

export function UsersListPage() {
  const role = useAuthStore((s) => s.user?.role);
  const isOwner = role === "owner";

  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<Role | "">("");
  const [activeFilter, setActiveFilter] = useState<"" | "true" | "false">("");
  const [items, setItems] = useState<UserResponse[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Debounce the search input.
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Reset pagination on filter changes.
  useEffect(() => {
    setCursor(null);
  }, [search, roleFilter, activeFilter]);

  const params = useMemo(() => {
    const p: Record<string, string> = {};
    if (search) p["search"] = search;
    if (roleFilter) p["role"] = roleFilter;
    if (activeFilter !== "") p["is_active"] = activeFilter;
    if (cursor) p["cursor"] = cursor;
    return p;
  }, [search, roleFilter, activeFilter, cursor]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .get("/api/v1/users", { params })
      .then((res) => {
        if (cancelled) return;
        setItems(res.data.items);
        setNextCursor(res.data.next_cursor ?? null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail ?? "Failed to load users.";
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [params]);

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Users</h1>
        {isOwner ? (
          <Button asChild>
            <Link to="/admin/users/new">New user</Link>
          </Button>
        ) : null}
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="users-search" className="text-xs font-medium">
            Search
          </label>
          <Input
            id="users-search"
            placeholder="email or name"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="users-role" className="text-xs font-medium">
            Role
          </label>
          <select
            id="users-role"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value as Role | "")}
          >
            <option value="">All roles</option>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="users-active" className="text-xs font-medium">
            Status
          </label>
          <select
            id="users-active"
            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
            value={activeFilter}
            onChange={(e) =>
              setActiveFilter(e.target.value as "" | "true" | "false")
            }
          >
            <option value="">All</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
        </div>
      </div>

      {error ? (
        <div
          role="alert"
          data-testid="users-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <table className="w-full table-fixed border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-2">Email</th>
            <th className="py-2 pr-2">Name</th>
            <th className="py-2 pr-2">Role</th>
            <th className="py-2 pr-2">Status</th>
            <th className="py-2 pr-2">Last login</th>
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
                No users match the current filters.
              </td>
            </tr>
          ) : (
            items.map((u) => (
              <tr key={u.id} className="border-b border-border/50">
                <td className="py-2 pr-2">
                  <Link to={`/admin/users/${u.id}`} className="hover:underline">
                    {u.email}
                  </Link>
                </td>
                <td className="py-2 pr-2">{u.full_name}</td>
                <td className="py-2 pr-2">{u.role}</td>
                <td className="py-2 pr-2">
                  {u.is_active ? "Active" : "Inactive"}
                </td>
                <td className="py-2 pr-2">
                  {u.last_login
                    ? new Date(u.last_login).toLocaleString()
                    : "—"}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      {nextCursor ? (
        <div className="flex justify-end">
          <Button
            variant="outline"
            onClick={() => setCursor(nextCursor)}
            data-testid="load-more"
          >
            Load more
          </Button>
        </div>
      ) : null}
    </section>
  );
}
