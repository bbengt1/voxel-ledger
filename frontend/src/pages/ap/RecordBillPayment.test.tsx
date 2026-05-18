import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { RecordBillPaymentPage } from "@/pages/ap/RecordBillPayment";
import { useAuthStore } from "@/store/useAuthStore";

const VENDOR_ID = "11111111-1111-1111-1111-111111111111";
const BILL_ID = "22222222-2222-2222-2222-222222222222";
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
    <MemoryRouter initialEntries={["/bill-payments/new"]}>
      <AppProviders>
        <Routes>
          <Route path="/bill-payments/new" element={<RecordBillPaymentPage />} />
          <Route path="/bill-payments/:id" element={<div>bp-detail</div>} />
          <Route path="/bill-payments" element={<div>bp-list</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

function makeBill(state: string) {
  return {
    id: BILL_ID,
    bill_number: "BILL-2026-0001",
    vendor_id: VENDOR_ID,
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
    vendor_invoice_number: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    created_by_user_id: "u",
  };
}

describe("<RecordBillPaymentPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/vendors").reply(200, {
      items: [
        {
          id: VENDOR_ID,
          vendor_number: "VND-0001",
          display_name: "Acme",
          legal_name: null,
          primary_email: null,
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
    mock.onGet("/api/v1/bills").reply((config) => {
      const params = config.params as Record<string, string>;
      const state = params["state"];
      const items = state === "issued" ? [makeBill("issued")] : [];
      return [200, { items, next_cursor: null }];
    });
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("picks vendor, allocates against an open bill, and submits", async () => {
    const user = userEvent.setup();
    let createBody: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/bill-payments").reply((config) => {
      createBody = JSON.parse(config.data as string);
      return [
        201,
        {
          id: PAYMENT_ID,
          payment_number: "BPM-2026-0001",
          vendor_id: VENDOR_ID,
          state: "pending",
          amount: createBody?.["amount"],
          method: createBody?.["method"],
          reference_number: null,
          notes: null,
          applications: [],
          occurred_at: "2026-05-01T00:00:00Z",
          posting_journal_entry_id: null,
          created_at: "2026-05-01T00:00:00Z",
          updated_at: "2026-05-01T00:00:00Z",
          created_by_user_id: "u",
        },
      ];
    });

    renderPage();

    await user.click(screen.getByTestId("bill-payment-vendor-picker-input"));
    await waitFor(() =>
      expect(
        screen.getByTestId(`bill-payment-vendor-picker-option-${VENDOR_ID}`),
      ).toBeInTheDocument(),
    );
    await user.click(
      screen.getByTestId(`bill-payment-vendor-picker-option-${VENDOR_ID}`),
    );

    await waitFor(() =>
      expect(screen.getByTestId(`alloc-row-${BILL_ID}`)).toBeInTheDocument(),
    );

    await user.clear(screen.getByTestId("bill-payment-amount"));
    await user.type(screen.getByTestId("bill-payment-amount"), "50");

    await user.type(screen.getByTestId(`alloc-input-${BILL_ID}`), "50");

    await user.click(screen.getByTestId("record-bill-payment-submit"));

    await waitFor(() => expect(createBody).toBeDefined());
    expect(createBody?.["vendor_id"]).toBe(VENDOR_ID);
    expect(createBody?.["amount"]).toBe("50");

    const apps = createBody?.["applications"] as Array<{
      bill_id: string;
      amount_applied: string;
    }>;
    expect(apps).toHaveLength(1);
    expect(apps[0]?.bill_id).toBe(BILL_ID);
    expect(apps[0]?.amount_applied).toBe("50");
  });
});
