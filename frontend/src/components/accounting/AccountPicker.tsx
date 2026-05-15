/**
 * Autocomplete picker for accounts.
 *
 * Searches by code OR name via the accounts list endpoint. Mirrors the
 * EntityPicker pattern from inventory — debounced search, outside-click
 * close, keyboard-accessible options.
 */
import { useEffect, useRef, useState } from "react";

import { api } from "@/api/typed";
import type { components } from "@/api/types";
import { Input } from "@/components/ui/Input";

type AccountResponse = components["schemas"]["AccountResponse"];

export interface AccountOption {
  id: string;
  code: string;
  name: string;
  type: AccountResponse["type"];
}

interface Props {
  value: AccountOption | null;
  onChange: (option: AccountOption | null) => void;
  id?: string;
  placeholder?: string;
  disabled?: boolean;
  "data-testid"?: string;
}

const DEBOUNCE_MS = 200;

function labelFor(opt: AccountOption): string {
  return `${opt.code} — ${opt.name}`;
}

export function AccountPicker({
  value,
  onChange,
  id,
  placeholder,
  disabled,
  "data-testid": testId,
}: Props) {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [options, setOptions] = useState<AccountOption[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    const params: Record<string, string> = { is_archived: "false" };
    if (search.trim()) params["search"] = search.trim();
    api
      .get("/api/v1/accounts", { params })
      .then((res) => {
        if (cancelled) return;
        const items = res.data.items;
        setOptions(
          items.slice(0, 25).map((acc) => ({
            id: acc.id,
            code: acc.code,
            name: acc.name,
            type: acc.type,
          })),
        );
      })
      .catch(() => {
        if (!cancelled) setOptions([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [search, open]);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  function pick(opt: AccountOption) {
    onChange(opt);
    setSearchInput(labelFor(opt));
    setOpen(false);
  }

  return (
    <div className="relative" ref={containerRef} data-testid={testId}>
      <Input
        id={id}
        value={value ? labelFor(value) : searchInput}
        placeholder={placeholder ?? "Search by code or name…"}
        disabled={disabled}
        onChange={(e) => {
          if (value) onChange(null);
          setSearchInput(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        autoComplete="off"
        data-testid={testId ? `${testId}-input` : undefined}
      />
      {open ? (
        <ul
          className="absolute z-50 mt-1 max-h-56 w-full overflow-y-auto rounded-md border border-border bg-background text-sm shadow"
          role="listbox"
          data-testid={testId ? `${testId}-options` : undefined}
        >
          {loading && options.length === 0 ? (
            <li className="px-2 py-1.5 text-muted-foreground">Loading…</li>
          ) : options.length === 0 ? (
            <li className="px-2 py-1.5 text-muted-foreground">No matches.</li>
          ) : (
            options.map((opt) => (
              <li key={opt.id}>
                <button
                  type="button"
                  className="block w-full px-2 py-1.5 text-left hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:outline-none"
                  onClick={() => pick(opt)}
                  data-testid={testId ? `${testId}-option-${opt.id}` : undefined}
                >
                  <span className="font-mono text-xs">{opt.code}</span>{" "}
                  <span>{opt.name}</span>{" "}
                  <span className="text-xs text-muted-foreground">
                    ({opt.type})
                  </span>
                </button>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}
