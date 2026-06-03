import { type ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface FilterBarProps {
  children: ReactNode;
  /**
   * Max columns at the widest breakpoint. The grid steps
   * 1 → 2 (`sm`) → N (`lg`), so filters stack on phones and spread on desktop.
   * Defaults to 4.
   */
  columns?: 2 | 3 | 4 | 5;
  className?: string;
}

const LG_COLS: Record<NonNullable<FilterBarProps["columns"]>, string> = {
  2: "lg:grid-cols-2",
  3: "lg:grid-cols-3",
  4: "lg:grid-cols-4",
  5: "lg:grid-cols-5",
};

/**
 * Standardizes the filter-row grid (epic #320): one column on phones, two at
 * `sm`, up to N at `lg`. Replaces the ad-hoc
 * `grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4` scattered across list pages.
 */
export function FilterBar({ children, columns = 4, className }: FilterBarProps) {
  return (
    <div
      className={cn(
        "grid grid-cols-1 gap-3 sm:grid-cols-2",
        LG_COLS[columns],
        className,
      )}
      data-testid="filter-bar"
    >
      {children}
    </div>
  );
}
