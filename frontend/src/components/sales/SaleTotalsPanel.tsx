/**
 * Sticky totals panel for the sale composer. Pure presentational.
 */
import type { components } from "@/api/types";

import type { SaleTotals } from "./totals";

type SalesChannelResponse = components["schemas"]["SalesChannelResponse"];

interface Props {
  totals: SaleTotals;
  channel: SalesChannelResponse | null;
}

function money(n: number): string {
  return `$${n.toFixed(2)}`;
}

export function SaleTotalsPanel({ totals, channel }: Props) {
  return (
    <aside
      className="sticky top-4 h-fit w-72 shrink-0 space-y-2 rounded-lg border border-border p-4 text-sm"
      data-testid="sale-totals-panel"
    >
      <h2 className="text-sm font-semibold">Totals</h2>
      <dl className="grid grid-cols-2 gap-y-1">
        <dt className="text-muted-foreground">Subtotal</dt>
        <dd className="text-right font-mono" data-testid="totals-subtotal">
          {money(totals.subtotal)}
        </dd>
        <dt className="text-muted-foreground">Discount</dt>
        <dd className="text-right font-mono" data-testid="totals-discount">
          −{money(totals.discount)}
        </dd>
        <dt className="text-muted-foreground">Shipping</dt>
        <dd className="text-right font-mono" data-testid="totals-shipping">
          {money(totals.shipping)}
        </dd>
        <dt className="text-muted-foreground">Tax</dt>
        <dd className="text-right font-mono" data-testid="totals-tax">
          {money(totals.tax)}
        </dd>
        <dt className="text-muted-foreground">
          Channel fee
          {channel ? (
            <span className="ml-1 text-xs">({channel.fee_model})</span>
          ) : null}
        </dt>
        <dd className="text-right font-mono" data-testid="totals-fee">
          {money(totals.channelFee)}
        </dd>
      </dl>
      <div className="flex justify-between border-t border-border pt-2 font-semibold">
        <span>Total</span>
        <span className="font-mono" data-testid="totals-total">
          {money(totals.total)}
        </span>
      </div>
    </aside>
  );
}
