import { type ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface PageHeaderProps {
  title: ReactNode;
  /** Right-aligned actions (buttons/links). Stack under the title on phones. */
  actions?: ReactNode;
  /** Optional subtitle/description under the title. */
  description?: ReactNode;
  className?: string;
}

/**
 * Page title + actions row (epic #320). On phones the title and actions stack
 * vertically; from `sm:` they sit on one row with actions pushed right.
 * Replaces the repeated `flex flex-wrap items-center justify-between` headers.
 */
export function PageHeader({ title, actions, description, className }: PageHeaderProps) {
  return (
    <header
      className={cn(
        "flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between",
        className,
      )}
    >
      <div className="min-w-0">
        {typeof title === "string" ? (
          <h1 className="text-xl font-semibold">{title}</h1>
        ) : (
          title
        )}
        {description ? (
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex flex-wrap items-center gap-2 sm:flex-shrink-0">{actions}</div>
      ) : null}
    </header>
  );
}
