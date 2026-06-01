/**
 * Column-visibility control (#258). A small dropdown of checkboxes, one per
 * column, driven by `useColumnVisibility`. `alwaysVisible` columns render
 * checked + disabled.
 */
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import type { ColumnDef } from "@/lib/useColumnVisibility";

interface Props {
  columns: ColumnDef[];
  isVisible: (id: string) => boolean;
  toggle: (id: string, on: boolean) => void;
}

export function ColumnPicker({ columns, isVisible, toggle }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  return (
    <div className="relative" ref={ref}>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setOpen((o) => !o)}
        data-testid="column-picker-toggle"
        aria-expanded={open}
      >
        Columns
      </Button>
      {open ? (
        <div
          className="absolute right-0 z-10 mt-1 w-48 rounded-md border border-border bg-background p-2 shadow-md"
          data-testid="column-picker-menu"
        >
          <ul className="space-y-1">
            {columns.map((c) => (
              <li key={c.id}>
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={isVisible(c.id)}
                    disabled={c.alwaysVisible}
                    onChange={(e) => toggle(c.id, e.target.checked)}
                    data-testid={`column-toggle-${c.id}`}
                  />
                  {c.label}
                </label>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
