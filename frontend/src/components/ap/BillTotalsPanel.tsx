/**
 * Sticky totals panel for the bill composer. Mirrors `InvoiceTotalsPanel`
 * but uses AP test-ids.
 */
import type { ApDocTotals } from "./totals";

interface Props {
  totals: ApDocTotals;
  heading?: string;
}

function fmt(n: number) {
  return n.toFixed(2);
}

export function BillTotalsPanel({ totals, heading = "Totals" }: Props) {
  return (
    <aside
      className="sticky top-4 h-fit w-64 rounded-lg border border-border p-4 text-sm"
      data-testid="ap-totals-panel"
    >
      <h2 className="font-semibold">{heading}</h2>
      <dl className="mt-2 grid grid-cols-2 gap-y-1">
        <dt className="text-muted-foreground">Subtotal</dt>
        <dd className="text-right font-mono" data-testid="ap-totals-subtotal">
          ${fmt(totals.subtotal)}
        </dd>
        <dt className="text-muted-foreground">Discount</dt>
        <dd className="text-right font-mono" data-testid="ap-totals-discount">
          −${fmt(totals.discount)}
        </dd>
        <dt className="text-muted-foreground">Tax</dt>
        <dd className="text-right font-mono" data-testid="ap-totals-tax">
          ${fmt(totals.tax)}
        </dd>
        <dt className="font-semibold">Total</dt>
        <dd
          className="text-right font-mono font-semibold"
          data-testid="ap-totals-total"
        >
          ${fmt(totals.total)}
        </dd>
      </dl>
    </aside>
  );
}
