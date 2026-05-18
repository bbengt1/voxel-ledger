import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { BillDetailPage } from "@/pages/ap/BillDetail";
import { useAuthStore } from "@/store/useAuthStore";

const BILL_ID = "11111111-1111-1111-1111-111111111111";
const VENDOR_ID = "22222222-2222-2222-2222-222222222222";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/bills/${BILL_ID}`]}>
      <AppProviders>
        <Routes>
          <Route path="/bills/:id" element={<BillDetailPage />} />
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
    subtotal: "100.00",
    discount_amount: "0.00",
    tax_amount: "0.00",
    total_amount: "100.00",
    amount_paid: "0.00",
    amount_outstanding: "100.00",
    items: [],
    notes: null,
    due_at: null,
    issued_at: state === "draft" ? null : "2026-05-01T00:00:00Z",
    posting_journal_entry_id: null,
    billing_address_snapshot: null,
    vendor_invoice_number: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    created_by_user_id: "u",
  };
}

describe("<BillDetailPage />", () => {
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

  it("issues a draft bill via the issue modal", async () => {
    const user = userEvent.setup();
    let stateNow = "draft";
    mock.onGet(`/api/v1/bills/${BILL_ID}`).reply(() => [200, makeBill(stateNow)]);
    mock.onGet("/api/v1/accounts").reply(200, { items: [] });
    mock.onGet(`/api/v1/vendors/${VENDOR_ID}`).reply(200, {
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
    });
    let issued = false;
    mock.onPost(`/api/v1/bills/${BILL_ID}/issue`).reply(() => {
      issued = true;
      stateNow = "issued";
      return [200, {}];
    });

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("bill-state")).toHaveTextContent("draft"),
    );

    expect(screen.getByTestId("bill-pdf-link").getAttribute("href")).toBe(
      `/api/v1/bills/${BILL_ID}/pdf`,
    );

    await user.click(screen.getByTestId("action-issue"));
    await waitFor(() =>
      expect(screen.getByTestId("issue-bill-je-preview")).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId("issue-bill-confirm-btn"));

    await waitFor(() => expect(issued).toBe(true));
  });
});
