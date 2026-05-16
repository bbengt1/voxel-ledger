import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { InvoiceComposerPage } from "@/pages/ar/InvoiceComposer";
import { useAuthStore } from "@/store/useAuthStore";

const CUSTOMER_ID = "11111111-1111-1111-1111-111111111111";
const INVOICE_ID = "22222222-2222-2222-2222-222222222222";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/invoices/new"]}>
      <AppProviders>
        <Routes>
          <Route path="/invoices/new" element={<InvoiceComposerPage />} />
          <Route path="/invoices/:id" element={<div>invoice-detail</div>} />
          <Route path="/invoices" element={<div>invoices-list</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<InvoiceComposerPage />", () => {
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

  it("line totals update and save posts an invoice payload", async () => {
    const user = userEvent.setup();
    let postBody: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/invoices").reply((config) => {
      postBody = JSON.parse(config.data as string);
      return [
        201,
        {
          id: INVOICE_ID,
          invoice_number: "INV-2026-0001",
          customer_id: CUSTOMER_ID,
          state: "draft",
          currency: "USD",
          subtotal: "100.00",
          discount_amount: "0.00",
          tax_amount: "5.00",
          total_amount: "105.00",
          amount_paid: "0.00",
          amount_outstanding: "105.00",
          items: [],
          notes: null,
          due_at: null,
          issued_at: null,
          posting_journal_entry_id: null,
          billing_address_snapshot: null,
          quote_id: null,
          sale_id: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          created_by_user_id: "u",
        },
      ];
    });

    renderPage();

    await user.click(screen.getByTestId("invoice-customer-picker-input"));
    await waitFor(() => {
      expect(
        screen.getByTestId(`invoice-customer-picker-option-${CUSTOMER_ID}`),
      ).toBeInTheDocument();
    });
    await user.click(
      screen.getByTestId(`invoice-customer-picker-option-${CUSTOMER_ID}`),
    );

    await user.type(screen.getByTestId("line-0-description"), "Item");
    await user.clear(screen.getByTestId("line-0-quantity"));
    await user.type(screen.getByTestId("line-0-quantity"), "4");
    await user.clear(screen.getByTestId("line-0-unit-price"));
    await user.type(screen.getByTestId("line-0-unit-price"), "25");

    await user.clear(screen.getByTestId("invoice-tax"));
    await user.type(screen.getByTestId("invoice-tax"), "5");

    await waitFor(() => {
      expect(screen.getByTestId("ar-totals-subtotal")).toHaveTextContent(
        "$100.00",
      );
    });
    expect(screen.getByTestId("ar-totals-total")).toHaveTextContent("$105.00");

    await user.click(screen.getByTestId("save-draft-btn"));

    await waitFor(() => {
      expect(postBody).toBeDefined();
    });
    expect(postBody?.["customer_id"]).toBe(CUSTOMER_ID);
    expect(postBody?.["tax_amount"]).toBe("5");
  });
});
