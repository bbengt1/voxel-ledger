/**
 * Inventory transactions stub page (Phase 3.2, #51).
 *
 * The full ledger UI lands in Phase 3.4 (#53). This page exists so the
 * sidebar entry has somewhere to go and operators landing on the link
 * see a "what's coming" placeholder instead of a 404.
 */
export function TransactionsStubPage() {
  return (
    <div className="flex flex-col gap-4 p-6">
      <h1 className="text-2xl font-semibold tracking-tight">
        Inventory transactions
      </h1>
      <p className="text-sm text-muted-foreground">
        The transactions ledger UI lands in Phase 3.4. The API surface is
        already live at <code>/api/v1/inventory/transactions</code>.
      </p>
      <p className="text-sm text-muted-foreground">Coming in Phase 3.4.</p>
    </div>
  );
}
