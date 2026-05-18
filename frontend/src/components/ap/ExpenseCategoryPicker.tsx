/**
 * Select-backed picker for expense categories. Loads the active list once
 * and exposes a flat dropdown with code + name. Used by bill / recurring-
 * bill / expense-claim composers when an `expense_category` line is
 * selected.
 */
import { useEffect, useState } from "react";

import { api } from "@/api/typed";
import type { components } from "@/api/types";

type ExpenseCategoryResponse = components["schemas"]["ExpenseCategoryResponse"];

interface Props {
  value: string;
  onChange: (id: string) => void;
  id?: string;
  disabled?: boolean;
  placeholder?: string;
  "data-testid"?: string;
}

export function ExpenseCategoryPicker({
  value,
  onChange,
  id,
  disabled,
  placeholder,
  "data-testid": testId,
}: Props) {
  const [items, setItems] = useState<ExpenseCategoryResponse[]>([]);

  useEffect(() => {
    api
      .get("/api/v1/expense-categories", { params: { active: true } })
      .then((res) => {
        setItems(res.data.items);
      })
      .catch(() => {
        /* non-fatal */
      });
  }, []);

  return (
    <select
      id={id}
      className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      data-testid={testId}
    >
      <option value="">{placeholder ?? "— Pick a category —"}</option>
      {items.map((it) => (
        <option key={it.id} value={it.id}>
          {it.code} · {it.name}
        </option>
      ))}
    </select>
  );
}
