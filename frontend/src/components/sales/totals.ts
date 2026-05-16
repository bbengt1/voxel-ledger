/**
 * Pure helpers for computing sale totals client-side. Kept separate from
 * the React component to keep react-refresh happy.
 */
import type { components } from "@/api/types";

type SalesChannelResponse = components["schemas"]["SalesChannelResponse"];

export interface SaleTotals {
  subtotal: number;
  discount: number;
  shipping: number;
  tax: number;
  channelFee: number;
  total: number;
}

function feeFor(
  channel: SalesChannelResponse | null,
  subtotal: number,
): number {
  if (!channel) return 0;
  const pct = channel.fee_percent ? Number.parseFloat(channel.fee_percent) : 0;
  const flat = channel.fee_flat ? Number.parseFloat(channel.fee_flat) : 0;
  switch (channel.fee_model) {
    case "none":
      return 0;
    case "flat":
      return flat;
    case "percent":
      return subtotal * pct;
    case "percent_plus_flat":
      return subtotal * pct + flat;
  }
}

export function computeTotals(opts: {
  lineExtended: number[];
  discount: number;
  shipping: number;
  tax: number;
  channel: SalesChannelResponse | null;
}): SaleTotals {
  const subtotal = opts.lineExtended.reduce((acc, v) => acc + v, 0);
  const channelFee = feeFor(opts.channel, subtotal);
  const total = subtotal - opts.discount + opts.shipping + opts.tax;
  return {
    subtotal,
    discount: opts.discount,
    shipping: opts.shipping,
    tax: opts.tax,
    channelFee,
    total,
  };
}
