import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { BalanceSheetPage } from "@/pages/reports/BalanceSheet";
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
    <MemoryRouter initialEntries={["/reports/balance-sheet"]}>
      <AppProviders>
        <Routes>
          <Route path="/reports/balance-sheet" element={<BalanceSheetPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

function bsBody(imbalance: string) {
  return {
    as_of: "2026-05-20",
    division_id: null,
    asset_rows: [
      {
        account_id: "11111111-1111-1111-1111-111111111111",
        code: "1000",
        name: "Bank",
        depth: 0,
        section: "asset",
        balance: "100.00",
      },
    ],
    liability_rows: [],
    equity_rows: [],
    total_assets: "100.00",
    total_liabilities: "0.00",
    total_equity: "0.00",
    total_liabilities_and_equity: "0.00",
    imbalance,
  };
}

describe("<BalanceSheetPage />", () => {
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

  it("renders imbalance pill when residual is non-zero", async () => {
    mock.onGet("/api/v1/reports/balance-sheet").reply(200, bsBody("100.00"));
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("bs-imbalance")).toBeInTheDocument(),
    );
  });

  it("hides imbalance pill when residual is zero", async () => {
    mock.onGet("/api/v1/reports/balance-sheet").reply(200, bsBody("0.00"));
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("Liabilities + equity")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("bs-imbalance")).not.toBeInTheDocument();
  });
});
