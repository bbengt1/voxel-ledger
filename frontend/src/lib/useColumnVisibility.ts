/**
 * Per-user, per-table column visibility (#258).
 *
 * Columns are declared as `{ id, label, defaultVisible?, alwaysVisible? }`.
 * The chosen set is persisted server-side under the per-user preference key
 * `table_columns.<tableId>` so it follows the user across devices/sessions,
 * with a localStorage cache for instant first paint. Unknown/stale column
 * ids in a stored preference are ignored; `alwaysVisible` columns can never
 * be hidden.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import { apiClient } from "@/api/client";

export interface ColumnDef {
  id: string;
  label: string;
  /** Visible when the user has no stored preference. Defaults to true. */
  defaultVisible?: boolean;
  /** Cannot be hidden (e.g. a primary/identifier column). */
  alwaysVisible?: boolean;
}

interface StoredPref {
  visible: string[];
}

function prefKey(tableId: string): string {
  return `table_columns.${tableId}`;
}

function lsKey(tableId: string): string {
  return `voxel-ledger.${prefKey(tableId)}`;
}

function defaultVisibleIds(columns: ColumnDef[]): string[] {
  return columns
    .filter((c) => c.alwaysVisible || c.defaultVisible !== false)
    .map((c) => c.id);
}

/** Keep only ids that still exist as columns, and force-include any
 * alwaysVisible columns. */
function reconcile(columns: ColumnDef[], visible: string[]): string[] {
  const known = new Set(columns.map((c) => c.id));
  const kept = visible.filter((id) => known.has(id));
  const set = new Set(kept);
  for (const c of columns) if (c.alwaysVisible) set.add(c.id);
  return columns.map((c) => c.id).filter((id) => set.has(id));
}

export function useColumnVisibility(tableId: string, columns: ColumnDef[]) {
  // Stable signature so the effect doesn't re-run on every render when the
  // caller passes an inline array.
  const columnsKey = useMemo(
    () => columns.map((c) => `${c.id}:${c.alwaysVisible ? 1 : 0}:${c.defaultVisible === false ? 0 : 1}`).join("|"),
    [columns],
  );

  const [visibleIds, setVisibleIds] = useState<string[]>(() => {
    if (typeof window !== "undefined") {
      try {
        const raw = window.localStorage.getItem(lsKey(tableId));
        if (raw) {
          const parsed = JSON.parse(raw) as StoredPref;
          if (Array.isArray(parsed.visible))
            return reconcile(columns, parsed.visible);
        }
      } catch {
        /* ignore cache corruption */
      }
    }
    return defaultVisibleIds(columns);
  });

  // Load the server-side preference once (source of truth), reconciled
  // against the current column set.
  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<{ value: Partial<StoredPref> }>(
        `/api/v1/me/preferences/${prefKey(tableId)}`,
      )
      .then((res) => {
        if (cancelled) return;
        const stored = res.data?.value?.visible;
        if (Array.isArray(stored)) {
          setVisibleIds(reconcile(columns, stored));
        }
      })
      .catch(() => {
        /* non-fatal — keep cache/defaults */
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tableId, columnsKey]);

  const persist = useCallback(
    (next: string[]) => {
      const reconciled = reconcile(columns, next);
      setVisibleIds(reconciled);
      try {
        window.localStorage.setItem(
          lsKey(tableId),
          JSON.stringify({ visible: reconciled }),
        );
      } catch {
        /* ignore quota errors */
      }
      void apiClient
        .put(`/api/v1/me/preferences/${prefKey(tableId)}`, {
          value: { visible: reconciled },
        })
        .catch(() => {
          /* non-fatal — cache already updated; will re-sync next load */
        });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tableId, columnsKey],
  );

  const visibleSet = useMemo(() => new Set(visibleIds), [visibleIds]);

  const isVisible = useCallback(
    (id: string) => visibleSet.has(id),
    [visibleSet],
  );

  const toggle = useCallback(
    (id: string, on: boolean) => {
      const col = columns.find((c) => c.id === id);
      if (col?.alwaysVisible) return; // never hide
      const next = on
        ? [...visibleIds, id]
        : visibleIds.filter((v) => v !== id);
      persist(next);
    },
    [columns, visibleIds, persist],
  );

  return { columns, isVisible, toggle, visibleIds };
}
