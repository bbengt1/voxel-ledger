import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { QuoteComposerPage } from "@/pages/ar/QuoteComposer";
import { useAuthStore } from "@/store/useAuthStore";

const CUSTOMER_ID = "11111111-1111-1111-1111-111111111111";
const QUOTE_ID = "22222222-2222-2222-2222-222222222222";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/quotes/new"]}>
      <AppProviders>
        <Routes>
          <Route path="/quotes/new" element={<QuoteComposerPage />} />
          <Route path="/quotes/:id" element={<div>quote-detail</div>} />
          <Route path="/quotes" element={<div>quotes-list</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<QuoteComposerPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/jobs").reply(200, { items: [], next_cursor: null });
    mock.onGet("/api/v1/customers").reply(200, {
      items: [
        {
          id: CUSTOMER_ID,
          customer_number: "CUS-0001",
          display_name: "Acme",
          legal_name: null,
          primary_email: null,
          phone: null,
          payment_terms_days: 30,
          state: "active",
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
    });
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("updates totals when a line is added and saves draft", async () => {
    const user = userEvent.setup();
    let postBody: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/quotes").reply((config) => {
      postBody = JSON.parse(config.data as string);
      return [
        201,
        {
          id: QUOTE_ID,
          quote_number: "QUO-2026-0001",
          customer_id: CUSTOMER_ID,
          state: "draft",
          subtotal: "100.00",
          discount_amount: "0.00",
          tax_amount: "0.00",
          total_amount: "100.00",
          items: [],
          notes: null,
          valid_until: null,
          billing_address_snapshot: null,
          accepted_invoice_id: null,
          issued_at: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          created_by_user_id: "u",
        },
      ];
    });

    renderPage();

    // Open customer picker, pick the one option.
    await user.click(screen.getByTestId("quote-customer-picker-input"));
    await waitFor(() => {
      expect(
        screen.getByTestId(`quote-customer-picker-option-${CUSTOMER_ID}`),
      ).toBeInTheDocument();
    });
    await user.click(
      screen.getByTestId(`quote-customer-picker-option-${CUSTOMER_ID}`),
    );

    // Fill line 0 manual.
    await user.type(screen.getByTestId("line-0-description"), "Service");
    await user.clear(screen.getByTestId("line-0-quantity"));
    await user.type(screen.getByTestId("line-0-quantity"), "2");
    await user.clear(screen.getByTestId("line-0-unit-price"));
    await user.type(screen.getByTestId("line-0-unit-price"), "50");

    await waitFor(() => {
      expect(screen.getByTestId("ar-totals-subtotal")).toHaveTextContent(
        "$100.00",
      );
    });

    await user.click(screen.getByTestId("save-draft-btn"));

    await waitFor(() => {
      expect(postBody).toBeDefined();
    });
    expect(postBody?.["customer_id"]).toBe(CUSTOMER_ID);
    expect((postBody?.["items"] as unknown[]).length).toBe(1);
  });
});
