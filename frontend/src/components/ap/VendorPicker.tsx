/**
 * Debounced autocomplete picker for vendors. Mirrors CustomerPicker but
 * hits `/api/v1/vendors?search=`.
 */
import { useEffect, useRef, useState } from "react";

import { api } from "@/api/typed";
import { Input } from "@/components/ui/Input";

export interface VendorOption {
  id: string;
  label: string;
}

interface Props {
  value: VendorOption | null;
  onChange: (option: VendorOption | null) => void;
  id?: string;
  placeholder?: string;
  disabled?: boolean;
  "data-testid"?: string;
}

const DEBOUNCE_MS = 200;

export function VendorPicker({
  value,
  onChange,
  id,
  placeholder,
  disabled,
  "data-testid": testId,
}: Props) {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [options, setOptions] = useState<VendorOption[]>([]);
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
    const params: Record<string, string> = { state: "active" };
    if (search.trim()) params["search"] = search.trim();
    api
      .get("/api/v1/vendors", { params })
      .then((res) => {
        if (cancelled) return;
        const items = (
          res.data as {
            items: Array<{
              id: string;
              display_name: string;
              vendor_number: string;
            }>;
          }
        ).items;
        setOptions(
          items.slice(0, 20).map((it) => ({
            id: it.id,
            label: `${it.display_name} (${it.vendor_number})`,
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

  function pick(opt: VendorOption) {
    onChange(opt);
    setSearchInput(opt.label);
    setOpen(false);
  }

  return (
    <div className="relative" ref={containerRef} data-testid={testId}>
      <Input
        id={id}
        value={value ? value.label : searchInput}
        placeholder={placeholder ?? "Search vendors…"}
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
