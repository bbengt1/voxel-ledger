import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { DivisionsComparisonPage } from "@/pages/reports/DivisionsComparison";
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
    <MemoryRouter initialEntries={["/reports/divisions-comparison"]}>
      <AppProviders>
        <Routes>
          <Route
            path="/reports/divisions-comparison"
            element={<DivisionsComparisonPage />}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<DivisionsComparisonPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    mock = new MockAdapter(apiClient);
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders one column per division + an unallocated column", async () => {
    mock.onGet("/api/v1/reports/divisions-comparison").reply(200, {
      date_from: "2026-05-01",
      date_to: "2026-05-31",
      columns: [
        { division_id: "div-a", code: "A", label: "Alpha" },
        { division_id: "div-b", code: "B", label: "Bravo" },
        {
          division_id: "__unallocated__",
          code: "",
          label: "(unallocated)",
        },
      ],
      revenue_rows: [
        {
          account_id: "acct-1",
          code: "4000",
          name: "Sales",
          section: "revenue",
          amounts: {
            "div-a": "100.00",
            "div-b": "250.00",
            __unallocated__: "30.00",
          },
        },
      ],
      cogs_rows: [],
      operating_expense_rows: [],
      total_revenue: {
        "div-a": "100.00",
        "div-b": "250.00",
        __unallocated__: "30.00",
      },
      total_cogs: { "div-a": "0", "div-b": "0", __unallocated__: "0" },
      gross_profit: {
        "div-a": "100.00",
        "div-b": "250.00",
        __unallocated__: "30.00",
      },
      total_operating_expenses: {
        "div-a": "0",
        "div-b": "0",
        __unallocated__: "0",
      },
      operating_income: {
        "div-a": "100.00",
        "div-b": "250.00",
        __unallocated__: "30.00",
      },
      net_income: {
        "div-a": "100.00",
        "div-b": "250.00",
        __unallocated__: "30.00",
      },
    });
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("dc-col-div-a")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("dc-col-div-b")).toBeInTheDocument();
    expect(screen.getByTestId("dc-col-__unallocated__")).toBeInTheDocument();
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Bravo")).toBeInTheDocument();
    expect(screen.getByText("(unallocated)")).toBeInTheDocument();
  });
});
