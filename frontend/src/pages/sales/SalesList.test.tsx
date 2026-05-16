import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { SalesListPage } from "@/pages/sales/SalesList";
import { useAuthStore } from "@/store/useAuthStore";

const SALE_ID = "11111111-1111-1111-1111-111111111111";
const CHANNEL_ID = "22222222-2222-2222-2222-222222222222";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage(initial = "/sales") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <AppProviders>
        <Routes>
          <Route path="/sales" element={<SalesListPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<SalesListPage />", () => {
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
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders sales and filters by state via URL state", async () => {
    const user = userEvent.setup();
    let lastParams: Record<string, string> | undefined;
    mock.onGet("/api/v1/sales").reply((config) => {
      lastParams = config.params as Record<string, string>;
      return [
        200,
        {
          items: [
            {
              id: SALE_ID,
              sale_number: "SALE-2026-0001",
              channel_id: CHANNEL_ID,
              customer_name: "Acme Co",
              customer_email: null,
              external_order_id: null,
              state: lastParams?.["state"] ?? "draft",
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
              items: [],
              notes: null,
            },
          ],
          next_cursor: null,
        },
      ];
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("SALE-2026-0001")).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByTestId("filter-state"), "confirmed");

    await waitFor(() => {
      expect(lastParams?.["state"]).toBe("confirmed");
    });
  });
});
