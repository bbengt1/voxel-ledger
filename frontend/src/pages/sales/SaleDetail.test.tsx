import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { SaleDetailPage } from "@/pages/sales/SaleDetail";
import { useAuthStore } from "@/store/useAuthStore";

const SALE_ID = "11111111-1111-1111-1111-111111111111";
const CHANNEL_ID = "22222222-2222-2222-2222-222222222222";
const JE_ID = "33333333-3333-3333-3333-333333333333";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function baseSale(state: string, extra: Record<string, unknown> = {}) {
  return {
    id: SALE_ID,
    sale_number: "SALE-2026-0001",
    channel_id: CHANNEL_ID,
    customer_name: "Acme Co",
    customer_email: null,
    external_order_id: null,
    state,
    occurred_at: "2026-05-01T00:00:00Z",
    recorded_at: "2026-05-01T00:00:00Z",
    subtotal: "100.00",
    discount_amount: "0.00",
    shipping_amount: "0.00",
    tax_amount: "0.00",
    channel_fee_amount: "6.50",
    total_amount: "100.00",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    created_by_user_id: "u",
    items: [
      {
        id: "line-1",
        line_number: 1,
        kind: "manual",
        description: "Widget",
        quantity: "1.00",
        unit_price: "100.00",
        extended_amount: "100.00",
      },
    ],
    notes: null,
    ...extra,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/sales/${SALE_ID}`]}>
      <AppProviders>
        <Routes>
          <Route path="/sales/:id" element={<SaleDetailPage />} />
          <Route path="/sales" element={<div>sales-list</div>} />
          <Route
            path="/accounting/entries/:id"
            element={<div>je-detail</div>}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<SaleDetailPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("confirm flow shows the posted journal entry id", async () => {
    const user = userEvent.setup();
    // First fetch: draft sale.
    let state = "draft";
    mock.onGet(`/api/v1/sales/${SALE_ID}`).reply(() => {
      if (state === "draft") return [200, baseSale("draft")];
      return [
        200,
        baseSale("confirmed", { journal_entry_id: JE_ID }),
      ];
    });
    mock.onPost(`/api/v1/sales/${SALE_ID}/confirm`).reply(() => {
      state = "confirmed";
      return [200, baseSale("confirmed", { journal_entry_id: JE_ID })];
    });
    mock.onGet(`/api/v1/sales/${SALE_ID}/cogs-preview`).reply(200, {
      sale_id: SALE_ID,
      sale_number: "SALE-2026-0001",
      state: "confirmed",
      subtotal: "100.00",
      discount_amount: "0.00",
      shipping_amount: "0.00",
      tax_amount: "0.00",
      channel_fee_amount: "6.50",
      total_amount: "100.00",
      total_cost: "40.00",
      lines: [],
    });
    mock.onGet(`/api/v1/sales/${SALE_ID}/shipments`).reply(200, { items: [] });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("sale-state")).toHaveTextContent("draft");
    });

    await user.click(screen.getByTestId("transition-confirm"));

    await waitFor(() => {
      expect(screen.getByTestId("sale-state")).toHaveTextContent("confirmed");
    });

    await waitFor(() => {
      expect(screen.getByTestId("posted-journal-entry-id")).toHaveTextContent(
        JE_ID,
      );
    });
  });
});
