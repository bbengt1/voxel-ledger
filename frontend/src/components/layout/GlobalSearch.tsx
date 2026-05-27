/**
 * Top-bar global search combobox (#251).
 *
 * Hits ``GET /api/v1/search?q=<query>`` on a 200ms debounce, renders
 * the grouped results in a floating panel, and navigates to the
 * picked row's ``href`` on Enter or click. ``Cmd-K`` / ``Ctrl-K``
 * focuses the input from anywhere; ``Esc`` closes the panel.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import { Input } from "@/components/ui/Input";

interface SearchHit {
  kind: string;
  id: string;
  label: string;
  sublabel: string | null;
  href: string;
}

const KIND_LABELS: Record<string, string> = {
  product: "Products",
  material: "Materials",
  supply: "Supplies",
  customer: "Customers",
  vendor: "Vendors",
  sale: "Sales",
  invoice: "Invoices",
  quote: "Quotes",
  refund: "Refunds",
  job: "Jobs",
  bill: "Bills",
  printer: "Printers",
  channel: "Sales channels",
};

const KIND_ORDER = [
  "product",
  "material",
  "supply",
  "customer",
  "vendor",
  "sale",
  "invoice",
  "quote",
  "refund",
  "job",
  "bill",
  "printer",
  "channel",
];

export function GlobalSearch() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [value, setValue] = useState("");
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [highlight, setHighlight] = useState(0);

  // Cmd-K / Ctrl-K focuses the input from anywhere.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Debounced fetch. New keystroke cancels any in-flight request.
  useEffect(() => {
    const trimmed = value.trim();
    if (trimmed.length === 0) {
      setItems([]);
      setOpen(false);
      return;
    }
    setOpen(true);
    setLoading(true);
    const controller = new AbortController();
    const handle = window.setTimeout(() => {
      apiClient
        .get<{ items: SearchHit[] }>("/api/v1/search", {
          params: { q: trimmed },
          signal: controller.signal,
        })
        .then((res) => {
          setItems(res.data.items);
          setHighlight(0);
        })
        .catch(() => {
          /* aborted or transient — ignore */
        })
        .finally(() => setLoading(false));
    }, 200);
    return () => {
      window.clearTimeout(handle);
      controller.abort();
    };
  }, [value]);

  // Group results in display order so the keyboard-nav index lines up
  // with rendering.
  const grouped = useMemo(() => {
    const buckets = new Map<string, SearchHit[]>();
    for (const item of items) {
      if (!buckets.has(item.kind)) buckets.set(item.kind, []);
      buckets.get(item.kind)!.push(item);
    }
    return KIND_ORDER.filter((k) => buckets.has(k)).map((k) => ({
      kind: k,
      label: KIND_LABELS[k] ?? k,
      hits: buckets.get(k)!,
    }));
  }, [items]);

  const pick = useCallback(
    (hit: SearchHit) => {
      setOpen(false);
      setValue("");
      navigate(hit.href);
    },
    [navigate],
  );

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      setOpen(false);
      inputRef.current?.blur();
      return;
    }
    if (!open || items.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((i) => Math.min(items.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      const hit = items[highlight];
      if (hit) {
        e.preventDefault();
        pick(hit);
      }
    }
  }

  // Stable index across the flat ``items`` array; we use it to apply
  // the highlight inside the grouped render.
  let flatIdx = 0;

  return (
    <div className="relative w-full max-w-md">
      <Input
        ref={inputRef}
        type="search"
        placeholder="Search products, customers, sales… (⌘K)"
        aria-label="Global search"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onFocus={() => {
          if (value.trim().length > 0) setOpen(true);
        }}
        onBlur={() => {
          // Delay so a click inside the dropdown lands before the
          // dropdown unmounts.
          setTimeout(() => setOpen(false), 150);
        }}
        onKeyDown={onKeyDown}
        data-testid="global-search-input"
      />
      {open ? (
        <div
          className="absolute left-0 right-0 top-full z-30 mt-1 max-h-[70vh] overflow-y-auto rounded-md border border-border bg-popover shadow-lg"
          data-testid="global-search-results"
        >
          {loading && items.length === 0 ? (
            <p className="p-3 text-xs text-muted-foreground">Searching…</p>
          ) : items.length === 0 ? (
            <p className="p-3 text-xs text-muted-foreground">No matches.</p>
          ) : (
            <ul>
              {grouped.map((group) => (
                <li key={group.kind} className="border-b border-border/40 last:border-b-0">
                  <p className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {group.label}
                  </p>
                  <ul>
                    {group.hits.map((hit) => {
                      const myIdx = flatIdx++;
                      const isActive = myIdx === highlight;
                      return (
                        <li key={`${hit.kind}-${hit.id}`}>
                          <button
                            type="button"
                            onMouseDown={(e) => {
                              // Pre-empt the input's blur handler so the
                              // dropdown stays mounted long enough to
                              // navigate.
                              e.preventDefault();
                              pick(hit);
                            }}
                            onMouseEnter={() => setHighlight(myIdx)}
                            className={
                              "flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent " +
                              (isActive ? "bg-accent" : "")
                            }
                            data-testid={`global-search-pick-${hit.kind}-${hit.id}`}
                          >
                            <span className="min-w-0 flex-1 truncate">
                              {hit.label}
                            </span>
                            {hit.sublabel ? (
                              <span className="truncate font-mono text-xs text-muted-foreground">
                                {hit.sublabel}
                              </span>
                            ) : null}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
