/**
 * Simple `<select>`-backed picker for chart-of-accounts entries. Used by
 * the customer composer for default revenue / AR accounts.
 */
import { useEffect, useState } from "react";

import { api } from "@/api/typed";
import type { components } from "@/api/types";

type AccountResponse = components["schemas"]["AccountResponse"];

interface Props {
  value: string;
  onChange: (id: string) => void;
  filterType?: AccountResponse["type"] | undefined;
  id?: string | undefined;
  disabled?: boolean | undefined;
  placeholder?: string | undefined;
  /** Bump to force a refetch — useful after a sibling "Create account"
   * flow so a freshly-created account shows up in the options. */
  refreshKey?: number | undefined;
  "data-testid"?: string | undefined;
}

export function AccountPicker({
  value,
  onChange,
  filterType,
  id,
  disabled,
  placeholder,
  refreshKey,
  "data-testid": testId,
}: Props) {
  const [accounts, setAccounts] = useState<AccountResponse[]>([]);
  useEffect(() => {
    api
      .get("/api/v1/accounts")
      .then((res) => {
        const items = (res.data as { items: AccountResponse[] }).items ?? [];
        setAccounts(items.filter((a) => !a.is_archived));
      })
      .catch(() => {
        /* non-fatal */
      });
  }, [refreshKey]);

  const filtered = filterType
    ? accounts.filter((a) => a.type === filterType)
    : accounts;

  return (
    <select
      id={id}
      className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      data-testid={testId}
    >
      <option value="">{placeholder ?? "— Pick an account —"}</option>
      {filtered.map((a) => (
        <option key={a.id} value={a.id}>
          {a.code} · {a.name}
        </option>
      ))}
    </select>
  );
}
