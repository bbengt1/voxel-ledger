import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { CustomersListPage } from "@/pages/ar/CustomersList";
import { useAuthStore } from "@/store/useAuthStore";

const CUSTOMER_ID = "11111111-1111-1111-1111-111111111111";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/customers"]}>
      <AppProviders>
        <Routes>
          <Route path="/customers" element={<CustomersListPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<CustomersListPage />", () => {
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

  it("renders customers and toggles archived filter", async () => {
    const user = userEvent.setup();
    let lastParams: Record<string, string> | undefined;
    mock.onGet("/api/v1/customers").reply((config) => {
      lastParams = config.params as Record<string, string>;
      return [
        200,
        {
          items: [
            {
              id: CUSTOMER_ID,
              customer_number: "CUS-0001",
              display_name: "Acme Co",
              legal_name: null,
              primary_email: "hi@acme.test",
              phone: null,
              payment_terms_days: 30,
              state: lastParams?.["state"] ?? "active",
              billing_address: null,
              shipping_address: null,
              default_revenue_account_id: null,
              default_ar_account_id: null,
              tax_profile_id: null,
              notes: null,
              contacts: [],
              created_at: "2026-01-01T00:00:00Z",
              updated_at: "2026-01-01T00:00:00Z",
            },
          ],
        },
      ];
    });

    renderPage();

    await waitFor(() => {
      // DataTable renders a desktop table + mobile card, so cell text appears twice.
      expect(screen.getAllByText("Acme Co").length).toBeGreaterThanOrEqual(1);
    });
    expect(lastParams?.["state"]).toBe("active");

    await user.selectOptions(screen.getByTestId("filter-state"), "archived");
    await waitFor(() => {
      expect(lastParams?.["state"]).toBe("archived");
    });
  });
});
