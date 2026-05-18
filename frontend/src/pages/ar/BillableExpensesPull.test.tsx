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
const BILL_ITEM_ID = "33333333-3333-3333-3333-333333333333";

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

describe("InvoiceComposer billable-expenses pull flow", () => {
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
    mock.onGet("/api/v1/billable-expenses").reply(200, {
      items: [
        {
          source_kind: "bill_item",
          source_id: BILL_ITEM_ID,
          description: "Materials for site visit",
          amount: "50.00",
          markup_percent: "10",
          occurred_on: "2026-05-01",
          line_number: 1,
          bill_id: "bill-1",
          bill_number: "BILL-0001",
          claim_id: null,
          claim_number: null,
        },
      ],
    });
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("appends selected billable rows as new invoice lines tagged with billable_source", async () => {
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
          subtotal: "50.00",
          discount_amount: "0.00",
          tax_amount: "0.00",
          total_amount: "50.00",
          amount_paid: "0.00",
          amount_outstanding: "50.00",
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

    // Pick customer.
    await user.click(screen.getByTestId("invoice-customer-picker-input"));
    await waitFor(() =>
      expect(
        screen.getByTestId(`invoice-customer-picker-option-${CUSTOMER_ID}`),
      ).toBeInTheDocument(),
    );
    await user.click(
      screen.getByTestId(`invoice-customer-picker-option-${CUSTOMER_ID}`),
    );

    // Open the pull modal.
    await user.click(await screen.findByTestId("pull-billable-btn"));

    const rowKey = `bill_item:${BILL_ITEM_ID}`;
    await waitFor(() =>
      expect(screen.getByTestId(`pull-row-${rowKey}`)).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId(`pull-check-${rowKey}`));
    await user.click(screen.getByTestId("pull-billable-confirm-btn"));

    await waitFor(() =>
      expect(
        screen.getByDisplayValue("Materials for site visit"),
      ).toBeInTheDocument(),
    );

    await user.click(screen.getByTestId("save-draft-btn"));

    await waitFor(() => expect(postBody).toBeDefined());
    const items = postBody?.["items"] as Array<{
      description: string;
      billable_source?: { kind: string; id: string };
    }>;
    expect(items).toHaveLength(1);
    expect(items[0]?.description).toBe("Materials for site visit");
    expect(items[0]?.billable_source).toEqual({
      kind: "bill_item",
      id: BILL_ITEM_ID,
    });
  });
});
