import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { RecurringComposerPage } from "@/pages/ar/RecurringComposer";
import { useAuthStore } from "@/store/useAuthStore";

const CUSTOMER_ID = "11111111-1111-1111-1111-111111111111";
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
    <MemoryRouter initialEntries={["/recurring-invoices/new"]}>
      <AppProviders>
        <Routes>
          <Route
            path="/recurring-invoices/new"
            element={<RecurringComposerPage />}
          />
          <Route
            path="/recurring-invoices/:id"
            element={<div>recurring-detail</div>}
          />
          <Route
            path="/recurring-invoices"
            element={<div>recurring-list</div>}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<RecurringComposerPage />", () => {
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

  it("previews next issue and posts a correct payload", async () => {
    const user = userEvent.setup();
    let postBody: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/recurring-invoices").reply((config) => {
      postBody = JSON.parse(config.data as string);
      return [
        201,
        {
          id: TEMPLATE_ID,
          customer_id: CUSTOMER_ID,
          name: "Monthly retainer",
          cadence_kind: "monthly",
          cadence_interval: 1,
          start_at: "2026-06-01T00:00:00Z",
          end_at: null,
          next_issue_at: "2026-07-01T00:00:00Z",
          last_issued_at: null,
          auto_issue: false,
          currency: "USD",
          discount_amount: "0",
          tax_amount: "0",
          notes: null,
          state: "active",
          items: [],
          created_at: "2026-06-01T00:00:00Z",
          updated_at: "2026-06-01T00:00:00Z",
          created_by_user_id: "u",
        },
      ];
    });

    renderPage();

    await user.click(screen.getByTestId("recurring-customer-picker-input"));
    await waitFor(() => {
      expect(
        screen.getByTestId(`recurring-customer-picker-option-${CUSTOMER_ID}`),
      ).toBeInTheDocument();
    });
    await user.click(
      screen.getByTestId(`recurring-customer-picker-option-${CUSTOMER_ID}`),
    );

    await user.type(screen.getByTestId("recurring-name"), "Retainer");
    await user.selectOptions(
      screen.getByTestId("recurring-cadence-kind"),
      "monthly",
    );
    await user.clear(screen.getByTestId("recurring-cadence-interval"));
    await user.type(screen.getByTestId("recurring-cadence-interval"), "2");

    const startInput = screen.getByTestId("recurring-start-at");
    await user.type(startInput, "2026-06-01");

    // Preview text should appear once start is set.
    await waitFor(() => {
      expect(screen.getByTestId("recurring-next-preview")).toHaveTextContent(
        /Next will issue on/,
      );
    });

    await user.type(screen.getByTestId("line-0-description"), "Service");
    await user.clear(screen.getByTestId("line-0-quantity"));
    await user.type(screen.getByTestId("line-0-quantity"), "1");
    await user.clear(screen.getByTestId("line-0-unit-price"));
    await user.type(screen.getByTestId("line-0-unit-price"), "200");

    await user.click(screen.getByTestId("save-recurring-btn"));

    await waitFor(() => {
      expect(postBody).toBeDefined();
    });
    expect(postBody?.["customer_id"]).toBe(CUSTOMER_ID);
    expect(postBody?.["name"]).toBe("Retainer");
    expect(postBody?.["cadence_kind"]).toBe("monthly");
    expect(postBody?.["cadence_interval"]).toBe(2);
    expect((postBody?.["items"] as unknown[]).length).toBe(1);
  });
});
