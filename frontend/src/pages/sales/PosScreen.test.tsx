import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { PosScreenPage } from "@/pages/sales/PosScreen";
import { useAuthStore } from "@/store/useAuthStore";

const CHANNEL_ID = "11111111-1111-1111-1111-111111111111";
const CART_ID = "22222222-2222-2222-2222-222222222222";

function setSession() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u1", email: "c@x.com", role: "sales" },
  });
}

function emptyCart() {
  return {
    id: CART_ID,
    cart_discount_amount: "0",
    cashier_user_id: "u1",
    channel_id: CHANNEL_ID,
    created_at: "2026-05-15T00:00:00Z",
    discount_amount: "0",
    items: [],
    line_discount_total: "0",
    state: "open",
    subtotal: "0",
    total: "0",
    updated_at: "2026-05-15T00:00:00Z",
  };
}

function cartWithItem(qty = "1") {
  const base = emptyCart();
  base.items = [
    {
      id: "line-1",
      line_number: 1,
      description: "Widget A",
      discount_amount: "0",
      extended_amount: String(10 * Number(qty)),
      quantity: qty,
      sku: "WIDGET-A",
      unit_price: "10",
    },
  ] as never;
  base.subtotal = String(10 * Number(qty));
  base.total = String(10 * Number(qty));
  return base;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/sales/pos"]}>
      <AppProviders>
        <Routes>
          <Route path="/sales/pos" element={<PosScreenPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<PosScreenPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    setSession();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/sales-channels").reply(200, {
      items: [
        {
          id: CHANNEL_ID,
          name: "Storefront",
          slug: "storefront",
          kind: "pos",
          fee_model: "none",
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    mock.onPost("/api/v1/pos/carts").reply(201, emptyCart());
    // Stub window.print to avoid jsdom errors.
    Object.defineProperty(window, "print", {
      configurable: true,
      value: vi.fn(),
    });
  });
  afterEach(() => mock.restore());

  it("scan posts to /pos/carts/{id}/scan and renders the line within 500ms", async () => {
    let scanCalls = 0;
    mock.onPost(`/api/v1/pos/carts/${CART_ID}/scan`).reply(() => {
      scanCalls += 1;
      return [200, cartWithItem(String(scanCalls))];
    });

    renderPage();
    const input = await screen.findByTestId("pos-scan-input");

    const start = performance.now();
    await userEvent.type(input, "WIDGET-A{Enter}");
    const line = await screen.findByTestId("cart-line-1");
    const elapsed = performance.now() - start;
    expect(elapsed).toBeLessThan(500);
    expect(line).toHaveTextContent("Widget A");
  });

  it("second scan of the same barcode increments quantity", async () => {
    let scanCalls = 0;
    mock.onPost(`/api/v1/pos/carts/${CART_ID}/scan`).reply(() => {
      scanCalls += 1;
      return [200, cartWithItem(String(scanCalls))];
    });

    renderPage();
    const input = await screen.findByTestId("pos-scan-input");
    await userEvent.type(input, "WIDGET-A{Enter}");
    await screen.findByTestId("cart-line-1");

    await userEvent.type(input, "WIDGET-A{Enter}");
    await waitFor(() => expect(scanCalls).toBe(2));
    await waitFor(() => {
      const cell = screen.getByTestId("cart-line-1");
      expect(cell).toHaveTextContent("2");
    });
  });

  it("F9 opens the checkout modal and tendered → change-due updates live", async () => {
    mock
      .onPost(`/api/v1/pos/carts/${CART_ID}/scan`)
      .reply(200, cartWithItem("1"));
    renderPage();
    const input = await screen.findByTestId("pos-scan-input");
    await userEvent.type(input, "WIDGET-A{Enter}");
    await screen.findByTestId("cart-line-1");

    // Fire F9 at the window level (matches the page's global hotkey handler).
    fireEvent.keyDown(window, { key: "F9" });
    const modal = await screen.findByTestId("checkout-modal");
    expect(modal).toBeInTheDocument();

    const tendered = screen.getByTestId("checkout-tendered") as HTMLInputElement;
    // Clear out the default-prefilled value, then type a fresh amount.
    await userEvent.clear(tendered);
    await userEvent.type(tendered, "25");
    const change = screen.getByTestId("checkout-change");
    // Total = 10, tendered = 25 → change-due = $15.00.
    expect(change).toHaveTextContent("$15.00");
  });
});
