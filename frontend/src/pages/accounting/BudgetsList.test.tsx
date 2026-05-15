import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { BudgetsListPage } from "@/pages/accounting/BudgetsList";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@x.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AppProviders>
        <BudgetsListPage />
      </AppProviders>
    </MemoryRouter>,
  );
}

const TODAY = new Date().toISOString().slice(0, 10);

describe("<BudgetsListPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/accounting/periods").reply(200, {
      items: [
        {
          id: "p-current",
          name: "Current",
          start_date: "2000-01-01",
          end_date: "2099-12-31",
          state: "open",
          closed_at: null,
          closed_by_user_id: null,
          locked_at: null,
          locked_by_user_id: null,
          created_at: TODAY,
          updated_at: TODAY,
        },
      ],
      next_cursor: null,
    });
    mock
      .onGet("/api/v1/accounting/divisions")
      .reply(200, { items: [], next_cursor: null });
  });

  afterEach(() => mock.restore());

  it("selects the current open period by default and renders variance rows", async () => {
    setOwner();
    mock.onGet("/api/v1/accounting/budgets/variance").reply((config) => {
      const params = config.params as Record<string, string>;
      expect(params["period_id"]).toBe("p-current");
      return [
        200,
        {
          period_id: "p-current",
          items: [
            {
              account_id: "acc-1",
              account_code: "6000",
              account_name: "Rent",
              account_type: "expense",
              division_id: null,
              division_name: null,
              budget_amount: "500.00",
              actual_amount: "200.00",
              variance: "300.00",
              variance_pct: "60.00",
            },
          ],
        },
      ];
    });
    renderPage();
    await waitFor(() =>
      expect(
        (screen.getByTestId("period-select") as HTMLSelectElement).value,
      ).toBe("p-current"),
    );
    expect(await screen.findByText("Rent")).toBeInTheDocument();
    const variance = await screen.findByTestId("variance-acc-1");
    // Expense w/ positive variance is favorable → emerald color class.
    expect(variance.className).toMatch(/emerald/);
  });

  it("opens the new-budget modal", async () => {
    setOwner();
    mock
      .onGet("/api/v1/accounting/budgets/variance")
      .reply(200, { period_id: "p-current", items: [] });
    renderPage();
    await screen.findByText(/No budgets for this period/i);
    await userEvent.click(screen.getByTestId("open-new-budget"));
    expect(await screen.findByTestId("new-budget-dialog")).toBeInTheDocument();
  });
});
