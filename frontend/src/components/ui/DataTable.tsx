import { type ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * One column of a {@link DataTable}. The same definition drives the desktop
 * table and the mobile card view, so a list page describes its columns once.
 */
export interface DataTableColumn<T> {
  /** Stable key (used for React keys + the mobile label fallback). */
  key: string;
  /** Header cell content (desktop) / field label (mobile). */
  header: ReactNode;
  /** Renders the cell for a row. */
  cell: (row: T) => ReactNode;
  align?: "left" | "right" | "center";
  /** This column's value becomes the card title on mobile. */
  isPrimary?: boolean;
  /** Omit this column from the mobile card (low-value/wide columns). */
  hideOnMobile?: boolean;
  /**
   * Render full-width at the bottom of the card with no label — for an
   * actions cell (buttons/menus) that reads awkwardly as "label: value".
   */
  cardFullWidth?: boolean;
  headerClassName?: string;
  cellClassName?: string;
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  getRowKey: (row: T) => string;
  loading?: boolean;
  emptyMessage?: string;
  /**
   * Minimum table width on desktop so columns don't crush; the wrapper scrolls
   * horizontally past this. Defaults to `min-w-[640px]`.
   */
  minWidthClassName?: string;
  stickyHeader?: boolean;
  className?: string;
  /** Optional extra classes per data row (desktop `<tr>` + mobile card). */
  rowClassName?: (row: T) => string | undefined;
}

/**
 * Responsive list primitive (epic #320). Desktop (`sm:+`) renders a real
 * `<table>` inside a horizontal-scroll wrapper so wide tables never overflow
 * the page; phones (`<sm`) get a stacked card per row (label → value), with
 * the `isPrimary` column as the card title. Both views are rendered and
 * toggled with CSS (`hidden`/`sm:block`) so there's no width-measure flash.
 */
export function DataTable<T>({
  columns,
  rows,
  getRowKey,
  loading = false,
  emptyMessage = "Nothing to show.",
  minWidthClassName = "min-w-[640px]",
  stickyHeader = false,
  className,
  rowClassName,
}: DataTableProps<T>) {
  const isEmpty = !loading && rows.length === 0;
  const alignClass = (a?: DataTableColumn<T>["align"]) =>
    a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left";

  const status = loading ? "Loading…" : isEmpty ? emptyMessage : null;

  return (
    <div className={className} data-testid="data-table">
      {/* Desktop: scroll-safe table. */}
      <div className="hidden overflow-x-auto sm:block">
        <table className={cn("w-full border-collapse text-sm", minWidthClassName)}>
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={cn(
                    "py-2 pr-2",
                    alignClass(col.align),
                    stickyHeader && "sticky top-0 bg-background",
                    col.headerClassName,
                  )}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {status ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="py-4 text-center text-muted-foreground"
                >
                  {status}
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr
                  key={getRowKey(row)}
                  className={cn("border-b border-border/50", rowClassName?.(row))}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={cn("py-2 pr-2", alignClass(col.align), col.cellClassName)}
                    >
                      {col.cell(row)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Mobile: a card per row. */}
      <div className="space-y-3 sm:hidden">
        {status ? (
          <p className="py-4 text-center text-sm text-muted-foreground">{status}</p>
        ) : (
          rows.map((row) => {
            const primary = columns.find((c) => c.isPrimary);
            const body = columns.filter(
              (c) => !c.hideOnMobile && !c.isPrimary && !c.cardFullWidth,
            );
            const fullWidth = columns.filter((c) => !c.hideOnMobile && c.cardFullWidth);
            return (
              <div
                key={getRowKey(row)}
                className={cn(
                  "rounded-lg border border-border p-3 text-sm",
                  rowClassName?.(row),
                )}
              >
                {primary ? (
                  <div className="mb-2 font-medium text-foreground">{primary.cell(row)}</div>
                ) : null}
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                  {body.map((col) => (
                    <div key={col.key} className="contents">
                      <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                        {col.header}
                      </dt>
                      <dd className={cn("text-foreground", alignClass(col.align))}>
                        {col.cell(row)}
                      </dd>
                    </div>
                  ))}
                </dl>
                {fullWidth.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2 border-t border-border/50 pt-3">
                    {fullWidth.map((col) => (
                      <div key={col.key}>{col.cell(row)}</div>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
