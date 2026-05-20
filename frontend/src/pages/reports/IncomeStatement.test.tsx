import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { IncomeStatementPage } from "@/pages/reports/IncomeStatement";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/reports/income-statement"]}>
      <AppProviders>
        <Routes>
          <Route path="/reports/income-statement" element={<IncomeStatementPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<IncomeStatementPage />", () => {
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

  it("renders sections and net-income total", async () => {
    mock.onGet("/api/v1/reports/income-statement").reply(200, {
      date_from: "2026-05-01",
      date_to: "2026-05-20",
      division_id: null,
      revenue_rows: [
        {
          account_id: "11111111-1111-1111-1111-111111111111",
          code: "4000",
          name: "Sales",
          depth: 0,
          section: "revenue",
          amount: "100.00",
        },
      ],
      cogs_rows: [],
      operating_expense_rows: [],
      total_revenue: "100.00",
      total_cogs: "0.00",
      gross_profit: "100.00",
      total_operating_expenses: "0.00",
      operating_income: "100.00",
      net_income: "100.00",
    });
    renderPage();

    await waitFor(() => expect(screen.getByText("Sales")).toBeInTheDocument());
    // Net income row is rendered.
    expect(screen.getByText("Net income")).toBeInTheDocument();
  });

  it("CSV download triggers an anchor click", async () => {
    mock.onGet("/api/v1/reports/income-statement").reply((config) => {
      if ((config.params as Record<string, unknown>)?.["format"] === "csv") {
        return [200, "section,account_code,...\n", { "content-type": "text/csv" }];
      }
      return [
        200,
        {
          date_from: "2026-05-01",
          date_to: "2026-05-20",
          division_id: null,
          revenue_rows: [],
          cogs_rows: [],
          operating_expense_rows: [],
          total_revenue: "0",
          total_cogs: "0",
          gross_profit: "0",
          total_operating_expenses: "0",
          operating_income: "0",
          net_income: "0",
        },
      ];
    });

    // jsdom doesn't ship URL.createObjectURL — install stubs.
    const createSpy = vi.fn().mockReturnValue("blob:fake");
    const revokeSpy = vi.fn();
    Object.assign(URL, {
      createObjectURL: createSpy,
      revokeObjectURL: revokeSpy,
    });

    renderPage();
    const user = userEvent.setup();
    const button = await screen.findByTestId("is-csv");
    await user.click(button);
    await waitFor(() => expect(createSpy).toHaveBeenCalled());
  });
});
