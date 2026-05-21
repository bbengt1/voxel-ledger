/**
 * `/dev/contrast-catalog` — every text-on-surface pair in the
 * Tailwind palette, in both light and dark themes (Phase 12.3b,
 * #213).
 *
 * Used by the Playwright a11y job (#213) to assert ``color-contrast``
 * passes WCAG AA. Lives under ``/dev`` so it doesn't show up in the
 * sidebar but is reachable for the operator + the test runner.
 */

const TEXT_TOKENS = [
  "text-foreground",
  "text-muted-foreground",
  "text-destructive",
  "text-primary",
  "text-primary-foreground",
  "text-accent-foreground",
  "text-secondary-foreground",
  "text-destructive-foreground",
] as const;

const SURFACE_TOKENS = [
  { label: "background", className: "bg-background" },
  { label: "muted", className: "bg-muted" },
  { label: "accent", className: "bg-accent" },
  { label: "primary", className: "bg-primary" },
  { label: "destructive", className: "bg-destructive" },
  { label: "card / border", className: "bg-background border border-border" },
] as const;

function Cell({
  textClass,
  surface,
}: {
  textClass: string;
  surface: (typeof SURFACE_TOKENS)[number];
}) {
  return (
    <div
      className={`${surface.className} ${textClass} p-3 rounded text-sm`}
      data-testid={`cc-${textClass}-on-${surface.label.replace(/[^a-z]/gi, "")}`}
    >
      <div className="font-medium">{textClass}</div>
      <div className="text-xs opacity-90">on {surface.label}</div>
      <div className="pt-1">The quick brown fox jumps over the lazy dog.</div>
    </div>
  );
}

export function ContrastCatalogPage() {
  return (
    <div className="space-y-6 p-6">
      <header>
        <h1 className="text-xl font-semibold">Contrast catalog</h1>
        <p className="pt-1 text-sm text-muted-foreground">
          Every Tailwind text-on-surface pair the app uses. Toggle the
          system theme to view the dark palette. Used by the Playwright
          a11y job to enforce WCAG AA contrast (4.5:1 / 3:1).
        </p>
      </header>
      {TEXT_TOKENS.map((textClass) => (
        <section key={textClass} className="space-y-2">
          <h2 className="text-sm font-medium uppercase text-muted-foreground">
            {textClass}
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {SURFACE_TOKENS.map((surface) => (
              <Cell
                key={surface.label}
                textClass={textClass}
                surface={surface}
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
