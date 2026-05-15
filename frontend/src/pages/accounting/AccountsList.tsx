/**
 * Stub page for the chart-of-accounts UI.
 *
 * Phase 4.1 (#64) lands the backend (account table, service, endpoints,
 * audit projection, events). The tree-view editor lands with #4.6
 * alongside the journal-entry composer; for now we surface a link in the
 * sidebar that routes here so the section grows incrementally.
 */
export function AccountsListPage() {
  return (
    <section
      data-testid="accounts-stub"
      className="rounded-lg border border-border bg-muted/30 p-6"
    >
      <h1 className="text-2xl font-semibold tracking-tight">
        Chart of accounts
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        The accounts API is live as of Phase 4.1. The tree-view editor is
        coming in #69 (Phase 4.6) alongside the journal-entry composer.
      </p>
    </section>
  );
}
