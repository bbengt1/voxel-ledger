import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { BillComposerPage } from "@/pages/ap/BillComposer";
import { useAuthStore } from "@/store/useAuthStore";

const VENDOR_ID = "11111111-1111-1111-1111-111111111111";
const BILL_ID = "22222222-2222-2222-2222-222222222222";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/bills/new"]}>
      <AppProviders>
        <Routes>
          <Route path="/bills/new" element={<BillComposerPage />} />
          <Route path="/bills/:id" element={<div>bill-detail</div>} />
          <Route path="/bills" element={<div>bills-list</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<BillComposerPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/accounts").reply(200, { items: [] });
    mock.onGet("/api/v1/expense-categories").reply(200, { items: [] });
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
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("updates totals as lines are entered and posts a bill payload", async () => {
    const user = userEvent.setup();
    let postBody: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/bills").reply((config) => {
      postBody = JSON.parse(config.data as string);
      return [
        201,
        {
          id: BILL_ID,
          bill_number: "BILL-2026-0001",
          vendor_id: VENDOR_ID,
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
          vendor_invoice_number: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          created_by_user_id: "u",
        },
      ];
    });

    renderPage();

    await user.click(screen.getByTestId("bill-vendor-picker-input"));
    await waitFor(() => {
      expect(
        screen.getByTestId(`bill-vendor-picker-option-${VENDOR_ID}`),
      ).toBeInTheDocument();
    });
    await user.click(
      screen.getByTestId(`bill-vendor-picker-option-${VENDOR_ID}`),
    );

    await user.type(screen.getByTestId("line-0-description"), "Item");
    await user.clear(screen.getByTestId("line-0-quantity"));
    await user.type(screen.getByTestId("line-0-quantity"), "4");
    await user.clear(screen.getByTestId("line-0-unit-price"));
    await user.type(screen.getByTestId("line-0-unit-price"), "25");

    await user.clear(screen.getByTestId("bill-tax"));
    await user.type(screen.getByTestId("bill-tax"), "5");

    await waitFor(() => {
      expect(screen.getByTestId("ap-totals-subtotal")).toHaveTextContent(
        "$100.00",
      );
    });
    expect(screen.getByTestId("ap-totals-total")).toHaveTextContent("$105.00");

    await user.click(screen.getByTestId("save-draft-btn"));

    await waitFor(() => {
      expect(postBody).toBeDefined();
    });
    expect(postBody?.["vendor_id"]).toBe(VENDOR_ID);
    expect(postBody?.["tax_amount"]).toBe("5");
    const items = postBody?.["items"] as Array<{
      kind: string;
      description: string;
    }>;
    expect(items).toHaveLength(1);
    expect(items[0]?.kind).toBe("manual");
  });
});
