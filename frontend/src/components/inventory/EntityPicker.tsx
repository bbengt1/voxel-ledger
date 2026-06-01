/**
 * Reusable autocomplete picker for materials / supplies / products.
 *
 * Queries the corresponding catalog list endpoint as the user types and
 * exposes the picked entity via `onChange`. Keeps a debounced search
 * input so we don't hammer the backend on every keystroke.
 */
import { useEffect, useRef, useState } from "react";

import { api } from "@/api/typed";
import { Input } from "@/components/ui/Input";

export type EntityKind = "material" | "supply" | "product" | "part";

export interface EntityOption {
  id: string;
  label: string;
}

interface Props {
  kind: EntityKind;
  value: EntityOption | null;
  onChange: (option: EntityOption | null) => void;
  /** Optional id to wire up label-for. */
  id?: string;
  placeholder?: string;
  disabled?: boolean;
  "data-testid"?: string;
}

const DEBOUNCE_MS = 200;

function endpointFor(kind: EntityKind) {
  if (kind === "material") return "/api/v1/materials" as const;
  if (kind === "supply") return "/api/v1/supplies" as const;
  if (kind === "part") return "/api/v1/parts" as const;
  return "/api/v1/products" as const;
}

function labelFor(
  kind: EntityKind,
  item: { id: string; name: string; sku?: string | null },
): string {
  if ((kind === "product" || kind === "part") && item.sku) {
    return `${item.name} (${item.sku})`;
  }
  return item.name;
}

export function EntityPicker({
  kind,
  value,
  onChange,
  id,
  placeholder,
  disabled,
  "data-testid": testId,
}: Props) {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [options, setOptions] = useState<EntityOption[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Debounce search input.
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Reset selection if the kind changes.
  const prevKind = useRef(kind);
  useEffect(() => {
    if (prevKind.current !== kind) {
      prevKind.current = kind;
      onChange(null);
      setSearchInput("");
      setSearch("");
    }
  }, [kind, onChange]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    const params: Record<string, string> = { is_archived: "false" };
    if (search.trim()) params["search"] = search.trim();
    api
      .get(endpointFor(kind), { params })
      .then((res) => {
        if (cancelled) return;
        const items = (
          res.data as {
            items: ReadonlyArray<{ id: string; name: string; sku?: string | null }>;
          }
        ).items;
        setOptions(
          items.slice(0, 20).map((item) => ({
            id: item.id,
            label: labelFor(kind, item),
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
  }, [kind, search, open]);

  // Close on outside click.
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  function pick(opt: EntityOption) {
    onChange(opt);
    setSearchInput(opt.label);
    setOpen(false);
  }

  return (
    <div className="relative" ref={containerRef} data-testid={testId}>
      <Input
        id={id}
        value={value ? value.label : searchInput}
        placeholder={placeholder ?? "Search…"}
        disabled={disabled}
        onChange={(e) => {
          // Typing clears a prior pick so the user can search again.
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
            <li className="px-2 py-1.5 text-muted-foreground">
              No matches.
            </li>
          ) : (
            options.map((opt) => (
              <li key={opt.id}>
                <button
                  type="button"
                  className="block w-full px-2 py-1.5 text-left hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:outline-none"
                  onClick={() => pick(opt)}
                  data-testid={testId ? `${testId}-option-${opt.id}` : undefined}
                >
                  {opt.label}
                </button>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}
