import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { SaleComposerPage } from "@/pages/sales/SaleComposer";
import { useAuthStore } from "@/store/useAuthStore";

const CHANNEL_ID = "22222222-2222-2222-2222-222222222222";
const PRODUCT_ID = "11111111-1111-1111-1111-111111111111";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/sales/new"]}>
      <AppProviders>
        <Routes>
          <Route path="/sales/new" element={<SaleComposerPage />} />
          <Route path="/sales/:id" element={<div>sale-detail</div>} />
          <Route path="/sales" element={<div>sales-list</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<SaleComposerPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/sales-channels").reply(200, {
      items: [
        {
          id: CHANNEL_ID,
          name: "Etsy",
          slug: "etsy",
          kind: "marketplace",
          fee_model: "percent",
          fee_percent: "0.065",
          fee_flat: null,
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          default_revenue_account_id: null,
          default_fee_account_id: null,
          external_id_format_hint: null,
        },
      ],
    });
    mock.onGet("/api/v1/jobs").reply(200, {
      items: [],
      next_cursor: null,
    });
    mock.onGet("/api/v1/products").reply(200, {
      items: [
        {
          id: PRODUCT_ID,
          name: "Widget",
          sku: "W-1",
          unit_price: "20.00",
          is_archived: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          description: null,
          category: null,
          upc: null,
          low_stock_threshold: null,
          weight_grams: null,
          custom_fields: null,
        },
      ],
      next_cursor: null,
    });
    mock.onGet(`/api/v1/products/${PRODUCT_ID}`).reply(200, {
      id: PRODUCT_ID,
      name: "Widget",
      sku: "W-1",
      unit_price: "20.00",
      is_archived: false,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      description: null,
      category: null,
      upc: null,
      low_stock_threshold: null,
      weight_grams: null,
      custom_fields: null,
    });
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("adds a product line and the totals panel updates with the channel fee", async () => {
    const user = userEvent.setup();
    renderPage();

    // Channel.
    await waitFor(() => {
      expect(screen.getByTestId("sale-channel")).toBeInTheDocument();
    });
    await user.selectOptions(screen.getByTestId("sale-channel"), CHANNEL_ID);

    // Switch line 0 to product, pick widget.
    await user.selectOptions(screen.getByTestId("line-0-kind"), "product");
    await user.click(screen.getByTestId("line-0-product-picker-input"));
    await waitFor(() => {
      expect(
        screen.getByTestId(`line-0-product-picker-option-${PRODUCT_ID}`),
      ).toBeInTheDocument();
    });
    await user.click(
      screen.getByTestId(`line-0-product-picker-option-${PRODUCT_ID}`),
    );

    // Description + unit price should be auto-filled.
    await waitFor(() => {
      expect(
        (screen.getByTestId("line-0-unit-price") as HTMLInputElement).value,
      ).toBe("20.00");
    });

    // 1 unit @ $20 → subtotal $20, fee = 20 * 0.065 = $1.30, total $20.
    expect(screen.getByTestId("totals-subtotal")).toHaveTextContent("$20.00");
    expect(screen.getByTestId("totals-fee")).toHaveTextContent("$1.30");
    expect(screen.getByTestId("totals-total")).toHaveTextContent("$20.00");
  });
});
