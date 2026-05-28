import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { BudgetVariancePage } from "@/pages/reports/BudgetVariance";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

const PERIOD_ID = "11111111-1111-1111-1111-111111111111";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/reports/budget-variance"]}>
      <AppProviders>
        <Routes>
          <Route
            path="/reports/budget-variance"
            element={<BudgetVariancePage />}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<BudgetVariancePage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    mock = new MockAdapter(apiClient);
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("auto-selects the first period and renders variance rows", async () => {
    mock.onGet("/api/v1/accounting/periods").reply(200, {
      items: [
        {
          id: PERIOD_ID,
          name: "Q1 2026",
          start_date: "2026-01-01",
          end_date: "2026-03-31",
          state: "open",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    mock.onGet("/api/v1/reports/budget-variance").reply(200, {
      period_id: PERIOD_ID,
      period_name: "Q1 2026",
      date_from: "2026-01-01",
      date_to: "2026-03-31",
      division_id: null,
      revenue_rows: [
        {
          account_id: "acct-rev",
          code: "4000",
          name: "Sales",
          section: "revenue",
          budget: "200.00",
          actual: "150.00",
          variance: "-50.00",
          variance_pct: "-25.00",
        },
      ],
      cogs_rows: [],
      operating_expense_rows: [
        {
          account_id: "acct-opex",
          code: "6000",
          name: "Rent",
          section: "operating_expenses",
          budget: "100.00",
          actual: "120.00",
          variance: "20.00",
          variance_pct: "20.00",
        },
      ],
      total_revenue_budget: "200.00",
      total_revenue_actual: "150.00",
      total_cogs_budget: "0.00",
      total_cogs_actual: "0.00",
      total_operating_expense_budget: "100.00",
      total_operating_expense_actual: "120.00",
    });

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("bv-pct-acct-rev")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("bv-pct-acct-rev")).toHaveTextContent("-25.00%");
    expect(screen.getByTestId("bv-pct-acct-opex")).toHaveTextContent("20.00%");
    // Period picker auto-selected.
    expect(
      (screen.getByTestId("bv-period") as HTMLSelectElement).value,
    ).toBe(PERIOD_ID);
  });
});
