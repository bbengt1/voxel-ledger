/**
 * Pure helpers for computing AR document totals (quote / invoice).
 *
 * Tax is operator-supplied — there is no automatic tax computation here.
 * Kept pure so it can be reused inside `useMemo` for sub-100ms recompute
 * on every keystroke.
 */
export interface ArDocTotals {
  subtotal: number;
  discount: number;
  tax: number;
  total: number;
}

export function computeArTotals(opts: {
  lineExtended: number[];
  discount: number;
  tax: number;
}): ArDocTotals {
  const subtotal = opts.lineExtended.reduce((acc, v) => acc + v, 0);
  const total = subtotal - opts.discount + opts.tax;
  return {
    subtotal,
    discount: opts.discount,
    tax: opts.tax,
    total,
  };
}
