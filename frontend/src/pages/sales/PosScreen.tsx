/**
 * Keyboard-first POS screen (Phase 6.7b).
 *
 * Doherty target: scan-to-line under 500ms; the scan input never blocks
 * waiting for the API — subsequent scans queue while the first call is
 * in-flight. A small spinner appears on the most recent scanned line if
 * the API takes longer than 100ms.
 *
 * Hotkeys:
 *   F2 — focus scan input
 *   F3 — apply discount (focus discount input)
 *   F4 — void cart
 *   F9 — open checkout modal
 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import type { AxiosError } from "axios";

import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/Dialog";
import type { components } from "@/api/types";

type PosCart = components["schemas"]["PosCartResponse"];
type SalesChannel = components["schemas"]["SalesChannelResponse"];
type CheckoutResponse = components["schemas"]["CheckoutResponse"];

interface ChannelListResponse {
  items: SalesChannel[];
}

function extractDetail(err: unknown, fallback: string): string {
  const ax = err as AxiosError<{ detail?: string }>;
  return ax?.response?.data?.detail ?? fallback;
}

function fmtMoney(value: string | number): string {
  const n = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(n)) return String(value);
  return n.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
  });
}

function ReceiptPrintBody({ payload }: { payload: CheckoutResponse }) {
  const sale = payload.sale;
  return (
    <div
      data-testid="receipt-print"
      className="hidden print:block print:p-4 print:text-xs"
    >
      <h1 className="text-base font-semibold">Receipt {sale.sale_number}</h1>
      <p>{new Date(sale.occurred_at).toLocaleString()}</p>
      {sale.customer_name && <p>Customer: {sale.customer_name}</p>}
      <hr className="my-2" />
      <table className="w-full">
        <tbody>
          {(payload.cart.items ?? []).map((item) => (
            <tr key={item.id}>
              <td>{item.description}</td>
              <td className="text-right">{item.quantity}</td>
              <td className="text-right">{fmtMoney(item.extended_amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <hr className="my-2" />
      <p>Subtotal: {fmtMoney(payload.cart.subtotal)}</p>
      <p>Total: {fmtMoney(payload.cart.total)}</p>
      <p>Change due: {fmtMoney(payload.change_due)}</p>
    </div>
  );
}

export function PosScreenPage() {
  const [cart, setCart] = useState<PosCart | null>(null);
  const [channels, setChannels] = useState<SalesChannel[]>([]);
  const [channelId, setChannelId] = useState<string>("");
  const [openingError, setOpeningError] = useState<string | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [scanValue, setScanValue] = useState("");
  /** Most-recently submitted barcodes that have an in-flight or queued API call. */
  const [pendingScans, setPendingScans] = useState<string[]>([]);
  /** Lines that should show the slow-API spinner because they exceeded 100ms. */
  const [slowLineNumbers, setSlowLineNumbers] = useState<Set<number>>(
    new Set(),
  );
  const [discount, setDiscount] = useState("");
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [tendered, setTendered] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("cash");
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [lastReceipt, setLastReceipt] = useState<CheckoutResponse | null>(null);

  const scanInputRef = useRef<HTMLInputElement | null>(null);
  const discountInputRef = useRef<HTMLInputElement | null>(null);
  const tenderedInputRef = useRef<HTMLInputElement | null>(null);
  /** Serializes scan API calls so subsequent scans queue rather than block input. */
  const scanQueueRef = useRef<Promise<void>>(Promise.resolve());

  // Load channels and open initial cart on mount.
  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<ChannelListResponse>("/api/v1/sales-channels", {
        params: { kind: "pos", active: true },
      })
      .then((res) => {
        if (cancelled) return;
        const items = res.data.items ?? [];
        setChannels(items);
        const first = items[0];
        if (first) {
          setChannelId(first.id);
        } else {
          setOpeningError(
            "No POS sales channel configured. Create one under Sales / Channels.",
          );
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setOpeningError(extractDetail(err, "Failed to load sales channels."));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const openCart = useCallback(
    async (cid: string) => {
      try {
        const res = await apiClient.post<PosCart>("/api/v1/pos/carts", {
          channel_id: cid,
        });
        setCart(res.data);
        setOpeningError(null);
        // Focus the scan input as soon as a cart is open.
        requestAnimationFrame(() => scanInputRef.current?.focus());
      } catch (err) {
        setOpeningError(extractDetail(err, "Failed to open cart."));
      }
    },
    [],
  );

  useEffect(() => {
    if (channelId && !cart) {
      void openCart(channelId);
    }
  }, [channelId, cart, openCart]);

  // Always refocus the scan input unless a modal/discount is being typed in.
  const refocusScan = useCallback(() => {
    if (checkoutOpen) return;
    if (document.activeElement === discountInputRef.current) return;
    scanInputRef.current?.focus();
  }, [checkoutOpen]);

  // Global hotkeys.
  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      if (e.key === "F2") {
        e.preventDefault();
        scanInputRef.current?.focus();
      } else if (e.key === "F3") {
        e.preventDefault();
        discountInputRef.current?.focus();
      } else if (e.key === "F4") {
        e.preventDefault();
        void voidCart();
      } else if (e.key === "F9") {
        e.preventDefault();
        if (cart && (cart.items?.length ?? 0) > 0) {
          setCheckoutOpen(true);
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cart]);

  const submitScan = useCallback(
    (barcode: string) => {
      if (!cart || !barcode.trim()) return;
      const trimmed = barcode.trim();
      setPendingScans((p) => [...p, trimmed]);

      // Mark slow if the request hasn't resolved in 100ms.
      let resolved = false;
      const slowTimer = window.setTimeout(() => {
        if (resolved) return;
        // Best-effort: tag the cart's last known line number plus one.
        setSlowLineNumbers((prev) => {
          const next = new Set(prev);
          next.add(-1); // sentinel = pending-not-yet-line
          return next;
        });
      }, 100);

      // Queue so concurrent scans serialize but don't block the input.
      scanQueueRef.current = scanQueueRef.current.then(async () => {
        try {
          const res = await apiClient.post<PosCart>(
            `/api/v1/pos/carts/${cart.id}/scan`,
            { barcode: trimmed },
          );
          setCart(res.data);
          setScanError(null);
        } catch (err) {
          setScanError(extractDetail(err, `Scan failed for ${trimmed}.`));
        } finally {
          resolved = true;
          window.clearTimeout(slowTimer);
          setPendingScans((p) => {
            const idx = p.indexOf(trimmed);
            if (idx < 0) return p;
            const next = [...p];
            next.splice(idx, 1);
            return next;
          });
          setSlowLineNumbers(new Set());
        }
      });
    },
    [cart],
  );

  function onScanSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!scanValue.trim()) return;
    submitScan(scanValue);
    setScanValue("");
  }

  function onScanKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    // Many barcode scanners emit a trailing Enter — handled by the form's onSubmit.
    // Hotkeys F-keys are caught at window level.
    if (e.key === "Escape") {
      setScanValue("");
    }
  }

  async function applyDiscount() {
    if (!cart) return;
    const value = discount.trim();
    if (!value) return;
    try {
      // Apply as a cart-level amount discount.
      const res = await apiClient.patch<PosCart>(
        `/api/v1/pos/carts/${cart.id}`,
        { discount_amount: value, discount_kind: "amount" },
      );
      setCart(res.data);
      setDiscount("");
      refocusScan();
    } catch (err) {
      setScanError(extractDetail(err, "Discount failed."));
    }
  }

  async function voidCart() {
    if (!cart) return;
    try {
      await apiClient.post(`/api/v1/pos/carts/${cart.id}/void`, {});
      setCart(null);
      setDiscount("");
      setScanError(null);
      if (channelId) {
        void openCart(channelId);
      }
    } catch (err) {
      setScanError(extractDetail(err, "Void failed."));
    }
  }

  async function charge() {
    if (!cart) return;
    setCheckoutBusy(true);
    setCheckoutError(null);
    try {
      const res = await apiClient.post<CheckoutResponse>(
        `/api/v1/pos/carts/${cart.id}/checkout`,
        {
          payment_method: paymentMethod,
          tendered_amount: tendered || "0",
          tax_amount: "0",
        },
      );
      setLastReceipt(res.data);
      // Print the receipt component (CSS-targeted print-only region).
      if (typeof window !== "undefined") {
        window.print();
      }
      setCheckoutOpen(false);
      setTendered("");
      setCart(null);
      if (channelId) {
        void openCart(channelId);
      }
    } catch (err) {
      setCheckoutError(extractDetail(err, "Checkout failed."));
    } finally {
      setCheckoutBusy(false);
    }
  }

  const total = cart ? Number(cart.total) : 0;
  const subtotal = cart ? Number(cart.subtotal) : 0;
  const cartDiscount = cart ? Number(cart.cart_discount_amount) : 0;
  const tenderedNum = Number(tendered || "0");
  const changeDue = Math.max(0, tenderedNum - total);

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Point of sale</h1>
        <div className="text-xs text-muted-foreground">
          Hotkeys: <kbd>F2</kbd> focus scan · <kbd>F3</kbd> discount ·{" "}
          <kbd>F4</kbd> void · <kbd>F9</kbd> checkout
        </div>
      </header>

      {openingError && (
        <div role="alert" className="rounded border border-destructive p-3 text-sm">
          {openingError}
        </div>
      )}

      {channels.length > 1 && (
        <label className="text-sm">
          Channel{" "}
          <select
            data-testid="pos-channel-select"
            value={channelId}
            onChange={(e) => {
              setChannelId(e.target.value);
              setCart(null);
            }}
            className="ml-2 rounded border border-border bg-background px-2 py-1"
          >
            {channels.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_280px]">
        <div className="flex flex-col gap-3">
          <form onSubmit={onScanSubmit} className="flex gap-2">
            <input
              ref={scanInputRef}
              data-testid="pos-scan-input"
              autoFocus
              value={scanValue}
              onChange={(e) => setScanValue(e.target.value)}
              onBlur={() => {
                // Re-focus on next tick — POS must keep the scan input active.
                setTimeout(refocusScan, 0);
              }}
              onKeyDown={onScanKeyDown}
              placeholder="Scan barcode…"
              className="h-12 flex-1 rounded border border-border bg-background px-3 text-lg"
              aria-label="Barcode"
            />
            <Button type="submit" size="lg">
              Add
            </Button>
          </form>

          {scanError && (
            <div role="alert" className="rounded border border-destructive p-3 text-sm">
              {scanError}
            </div>
          )}

          <div className="rounded border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="p-2">#</th>
                  <th className="p-2">SKU</th>
                  <th className="p-2">Description</th>
                  <th className="p-2 text-right">Qty</th>
                  <th className="p-2 text-right">Unit</th>
                  <th className="p-2 text-right">Ext.</th>
                </tr>
              </thead>
              <tbody>
                {(cart?.items ?? []).map((item) => {
                  const isSlow =
                    slowLineNumbers.has(-1) &&
                    item.line_number ===
                      Math.max(...(cart?.items ?? []).map((i) => i.line_number));
                  return (
                    <tr
                      key={item.id}
                      data-testid={`cart-line-${item.line_number}`}
                      className="border-t border-border"
                    >
                      <td className="p-2">{item.line_number}</td>
                      <td className="p-2">{item.sku ?? "—"}</td>
                      <td className="p-2">
                        {item.description}
                        {isSlow && (
                          <span
                            data-testid="line-spinner"
                            className="ml-2 inline-block h-3 w-3 animate-pulse rounded-full bg-muted-foreground/40"
                          />
                        )}
                      </td>
                      <td className="p-2 text-right">{item.quantity}</td>
                      <td className="p-2 text-right">
                        {fmtMoney(item.unit_price)}
                      </td>
                      <td className="p-2 text-right">
                        {fmtMoney(item.extended_amount)}
                      </td>
                    </tr>
                  );
                })}
                {(cart?.items ?? []).length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="p-4 text-center text-sm text-muted-foreground"
                    >
                      Cart is empty — scan a barcode to get started.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {pendingScans.length > 0 && (
            <p
              data-testid="pending-scans"
              className="text-xs text-muted-foreground"
            >
              Queued scans: {pendingScans.length}
            </p>
          )}
        </div>

        <aside
          aria-label="Totals"
          className="sticky top-4 flex h-fit flex-col gap-3 rounded border border-border p-3 text-sm"
        >
          <div className="flex justify-between">
            <span>Subtotal</span>
            <span>{fmtMoney(subtotal)}</span>
          </div>
          <div className="flex justify-between">
            <span>Discount</span>
            <span>-{fmtMoney(cartDiscount)}</span>
          </div>
          <div className="flex justify-between text-base font-semibold">
            <span>Total</span>
            <span data-testid="cart-total">{fmtMoney(total)}</span>
          </div>
          <div className="flex flex-col gap-2 pt-2">
            <label className="text-xs">
              Cart discount (amount)
              <div className="mt-1 flex gap-2">
                <input
                  ref={discountInputRef}
                  data-testid="pos-discount-input"
                  value={discount}
                  onChange={(e) => setDiscount(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      void applyDiscount();
                    }
                  }}
                  className="h-8 flex-1 rounded border border-border bg-background px-2"
                  inputMode="decimal"
                />
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => void applyDiscount()}
                >
                  Apply
                </Button>
              </div>
            </label>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              onClick={() => void voidCart()}
            >
              Void cart (F4)
            </Button>
            <Button
              type="button"
              size="lg"
              data-testid="pos-checkout-btn"
              disabled={!cart || (cart.items?.length ?? 0) === 0}
              onClick={() => {
                setCheckoutOpen(true);
                setTendered(String(total.toFixed(2)));
                requestAnimationFrame(() => tenderedInputRef.current?.focus());
              }}
            >
              Checkout (F9)
            </Button>
          </div>
        </aside>
      </div>

      <Dialog
        open={checkoutOpen}
        onOpenChange={(o) => {
          setCheckoutOpen(o);
          if (!o) {
            setCheckoutError(null);
            setTimeout(refocusScan, 0);
          }
        }}
      >
        <DialogContent data-testid="checkout-modal">
          <DialogTitle>Checkout</DialogTitle>
          <DialogDescription>
            Enter the tendered amount and charge the cart.
          </DialogDescription>
          <div className="mt-4 flex flex-col gap-3 text-sm">
            <div className="flex justify-between">
              <span>Total due</span>
              <span className="font-semibold">{fmtMoney(total)}</span>
            </div>
            <label className="flex flex-col gap-1">
              Payment method
              <select
                data-testid="checkout-method"
                value={paymentMethod}
                onChange={(e) => setPaymentMethod(e.target.value)}
                className="rounded border border-border bg-background px-2 py-1"
              >
                <option value="cash">Cash</option>
                <option value="card">Card</option>
                <option value="other">Other</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              Tendered amount
              <input
                ref={tenderedInputRef}
                data-testid="checkout-tendered"
                value={tendered}
                onChange={(e) => setTendered(e.target.value)}
                inputMode="decimal"
                className="rounded border border-border bg-background px-2 py-1"
              />
            </label>
            <div className="flex justify-between">
              <span>Change due</span>
              <span data-testid="checkout-change">{fmtMoney(changeDue)}</span>
            </div>
            {checkoutError && (
              <div role="alert" className="rounded border border-destructive p-2 text-xs">
                {checkoutError}
              </div>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  Cancel
                </Button>
              </DialogClose>
              <Button
                type="button"
                data-testid="checkout-charge"
                disabled={checkoutBusy}
                onClick={() => void charge()}
              >
                {checkoutBusy ? "Charging…" : "Charge"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {lastReceipt && <ReceiptPrintBody payload={lastReceipt} />}
    </section>
  );
}
