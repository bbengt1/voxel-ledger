/**
 * Pure helpers for computing bill totals. Mirrors the AR helper used by
 * invoice / quote composers. Kept pure so it can be reused inside
 * `useMemo` for sub-100ms recompute on every keystroke.
 */
export interface ApDocTotals {
  subtotal: number;
  discount: number;
  tax: number;
  total: number;
}

export function computeBillTotals(opts: {
  lineExtended: number[];
  discount: number;
  tax: number;
}): ApDocTotals {
  const subtotal = opts.lineExtended.reduce((acc, v) => acc + v, 0);
  const total = subtotal - opts.discount + opts.tax;
  return {
    subtotal,
    discount: opts.discount,
    tax: opts.tax,
    total,
  };
}
