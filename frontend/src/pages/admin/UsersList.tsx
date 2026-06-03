import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { FilterBar } from "@/components/ui/FilterBar";
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

  const columns: DataTableColumn<UserResponse>[] = [
    {
      key: "email",
      header: "Email",
      isPrimary: true,
      cell: (u) => (
        <Link to={`/admin/users/${u.id}`} className="hover:underline">
          {u.email}
        </Link>
      ),
    },
    { key: "name", header: "Name", cell: (u) => u.full_name },
    { key: "role", header: "Role", cell: (u) => u.role },
    {
      key: "status",
      header: "Status",
      cell: (u) => (u.is_active ? "Active" : "Inactive"),
    },
    {
      key: "last_login",
      header: "Last login",
      cell: (u) =>
        u.last_login ? new Date(u.last_login).toLocaleString() : "—",
    },
  ];

  return (
    <section className="flex flex-col gap-4">
      <PageHeader
        title="Users"
        actions={
          isOwner ? (
            <Button asChild>
              <Link to="/admin/users/new">New user</Link>
            </Button>
          ) : null
        }
      />

      <FilterBar columns={3}>
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
      </FilterBar>

      {error ? (
        <div
          role="alert"
          data-testid="users-error"
          className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <DataTable
        columns={columns}
        rows={items}
        getRowKey={(u) => u.id}
        loading={loading && items.length === 0}
        emptyMessage="No users match the current filters."
        minWidthClassName="min-w-[640px]"
      />

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
