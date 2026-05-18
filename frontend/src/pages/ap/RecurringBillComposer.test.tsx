import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { RecurringBillComposerPage } from "@/pages/ap/RecurringBillComposer";
import { useAuthStore } from "@/store/useAuthStore";

const VENDOR_ID = "11111111-1111-1111-1111-111111111111";
const TEMPLATE_ID = "22222222-2222-2222-2222-222222222222";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/recurring-bills/new"]}>
      <AppProviders>
        <Routes>
          <Route
            path="/recurring-bills/new"
            element={<RecurringBillComposerPage />}
          />
          <Route
            path="/recurring-bills/:id"
            element={<div>recurring-bill-detail</div>}
          />
          <Route
            path="/recurring-bills"
            element={<div>recurring-bills-list</div>}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<RecurringBillComposerPage />", () => {
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

  it("shows a next-issue preview and posts a template", async () => {
    const user = userEvent.setup();
    let postBody: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/recurring-bills").reply((config) => {
      postBody = JSON.parse(config.data as string);
      return [
        201,
        {
          id: TEMPLATE_ID,
          name: postBody?.["name"],
          vendor_id: VENDOR_ID,
          state: "active",
          currency: "USD",
          cadence_kind: postBody?.["cadence_kind"],
          cadence_interval: postBody?.["cadence_interval"],
          start_at: postBody?.["start_at"],
          end_at: null,
          auto_issue: false,
          discount_amount: "0.00",
          tax_amount: "0.00",
          notes: null,
          items: [],
          last_issued_at: null,
          next_issue_at: postBody?.["start_at"],
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          created_by_user_id: "u",
        },
      ];
    });

    renderPage();

    await user.click(
      screen.getByTestId("recurring-bill-vendor-picker-input"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId(
          `recurring-bill-vendor-picker-option-${VENDOR_ID}`,
        ),
      ).toBeInTheDocument(),
    );
    await user.click(
      screen.getByTestId(`recurring-bill-vendor-picker-option-${VENDOR_ID}`),
    );

    await user.type(screen.getByTestId("recurring-bill-name"), "Rent");
    await user.type(
      screen.getByTestId("recurring-bill-start-at"),
      "2026-06-01",
    );

    await waitFor(() =>
      expect(
        screen.getByTestId("recurring-bill-next-preview"),
      ).toHaveTextContent(/Next will issue on/),
    );

    await user.type(screen.getByTestId("line-0-description"), "Rent");
    await user.clear(screen.getByTestId("line-0-unit-price"));
    await user.type(screen.getByTestId("line-0-unit-price"), "1000");

    await user.click(screen.getByTestId("save-recurring-bill-btn"));

    await waitFor(() => expect(postBody).toBeDefined());
    expect(postBody?.["vendor_id"]).toBe(VENDOR_ID);
    expect(postBody?.["name"]).toBe("Rent");
    expect(postBody?.["cadence_kind"]).toBe("monthly");
    expect(postBody?.["cadence_interval"]).toBe(1);
  });
});
