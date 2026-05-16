import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { RecordPaymentPage } from "@/pages/ar/RecordPayment";
import { useAuthStore } from "@/store/useAuthStore";

const CUSTOMER_ID = "11111111-1111-1111-1111-111111111111";
const INVOICE_ID = "22222222-2222-2222-2222-222222222222";
const PAYMENT_ID = "33333333-3333-3333-3333-333333333333";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/payments/new"]}>
      <AppProviders>
        <Routes>
          <Route path="/payments/new" element={<RecordPaymentPage />} />
          <Route path="/payments/:id" element={<div>payment-detail</div>} />
          <Route path="/payments" element={<div>payments-list</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

function makeInvoice(state: string) {
  return {
    id: INVOICE_ID,
    invoice_number: "INV-2026-0001",
    customer_id: CUSTOMER_ID,
    state,
    currency: "USD",
    subtotal: "50.00",
    discount_amount: "0.00",
    tax_amount: "0.00",
    total_amount: "50.00",
    amount_paid: "0.00",
    amount_outstanding: "50.00",
    items: [],
    notes: null,
    due_at: null,
    issued_at: "2026-05-01T00:00:00Z",
    posting_journal_entry_id: null,
    billing_address_snapshot: null,
    quote_id: null,
    sale_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    created_by_user_id: "u",
  };
}

describe("<RecordPaymentPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
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
    mock.onGet("/api/v1/invoices").reply((config) => {
      const params = config.params as Record<string, string>;
      const state = params["state"];
      const items = state === "issued" ? [makeInvoice("issued")] : [];
      return [200, { items, next_cursor: null }];
    });
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("picks customer, allocates against an open invoice, and submits", async () => {
    const user = userEvent.setup();
    let createBody: Record<string, unknown> | undefined;
    let applyBody: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/payments").reply((config) => {
      createBody = JSON.parse(config.data as string);
      return [
        201,
        {
          id: PAYMENT_ID,
          payment_number: "PAY-2026-0001",
          customer_id: CUSTOMER_ID,
          state: "pending",
          amount: createBody?.["amount"],
          method: createBody?.["method"],
          reference: null,
          notes: null,
          applications: [],
          received_at: "2026-05-01T00:00:00Z",
          posting_journal_entry_id: null,
          created_at: "2026-05-01T00:00:00Z",
          updated_at: "2026-05-01T00:00:00Z",
          created_by_user_id: "u",
        },
      ];
    });
    mock.onPost(`/api/v1/payments/${PAYMENT_ID}/apply`).reply((config) => {
      applyBody = JSON.parse(config.data as string);
      return [200, {}];
    });

    renderPage();

    await user.click(screen.getByTestId("payment-customer-picker-input"));
    await waitFor(() => {
      expect(
        screen.getByTestId(`payment-customer-picker-option-${CUSTOMER_ID}`),
      ).toBeInTheDocument();
    });
    await user.click(
      screen.getByTestId(`payment-customer-picker-option-${CUSTOMER_ID}`),
    );

    await waitFor(() => {
      expect(screen.getByTestId(`alloc-row-${INVOICE_ID}`)).toBeInTheDocument();
    });

    await user.clear(screen.getByTestId("payment-amount"));
    await user.type(screen.getByTestId("payment-amount"), "50");

    await user.type(screen.getByTestId(`alloc-input-${INVOICE_ID}`), "50");

    await user.click(screen.getByTestId("record-payment-submit"));

    await waitFor(() => {
      expect(createBody).toBeDefined();
    });
    expect(createBody?.["customer_id"]).toBe(CUSTOMER_ID);
    expect(createBody?.["amount"]).toBe("50");

    await waitFor(() => {
      expect(applyBody).toBeDefined();
    });
    const apps = applyBody?.["applications"] as Array<{
      invoice_id: string;
      amount: string;
    }>;
    expect(apps).toHaveLength(1);
    expect(apps[0]?.invoice_id).toBe(INVOICE_ID);
    expect(apps[0]?.amount).toBe("50");
  });
});
