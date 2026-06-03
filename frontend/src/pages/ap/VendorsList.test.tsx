import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { VendorsListPage } from "@/pages/ap/VendorsList";
import { useAuthStore } from "@/store/useAuthStore";

const VENDOR_ID = "11111111-1111-1111-1111-111111111111";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/vendors"]}>
      <AppProviders>
        <Routes>
          <Route path="/vendors" element={<VendorsListPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<VendorsListPage />", () => {
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

  it("renders vendors returned by the API", async () => {
    mock.onGet("/api/v1/vendors").reply(200, {
      items: [
        {
          id: VENDOR_ID,
          vendor_number: "VND-0001",
          display_name: "Acme Supplies",
          legal_name: null,
          primary_email: "ar@acme.test",
          phone: null,
          payment_terms_days: 30,
          state: "active",
          billing_address: null,
          shipping_address: null,
          tax_id: null,
          is_1099_vendor: false,
          default_expense_account_id: null,
          default_ap_account_id: null,
          notes: null,
          contacts: [],
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    });

    renderPage();

    await waitFor(() => {
      // DataTable renders a desktop table + mobile card, so the vendor number
      // (and other cell text) appears twice in jsdom.
      expect(screen.getAllByText("VND-0001").length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getAllByText("Acme Supplies").length).toBeGreaterThanOrEqual(
      1,
    );
  });
});
