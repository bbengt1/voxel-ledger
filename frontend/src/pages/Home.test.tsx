import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { HomePage } from "@/pages/Home";
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
    <MemoryRouter initialEntries={["/"]}>
      <AppProviders>
        <Routes>
          <Route path="/" element={<HomePage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

const KPI_PAYLOAD = {
  as_of: "2026-05-20",
  // GL tiles are null since QBO replace-mode (#318 5d) — rendered as
  // "—" with an "In QuickBooks" hint.
  cash_on_hand: null,
  accounts_receivable: "500.00",
  accounts_payable: "200.00",
  overdue_invoice_count: 1,
  overdue_bill_count: 0,
  low_stock_alert_count: 2,
  net_income_mtd: null,
  net_income_ytd: null,
  last_updated_at: "2026-05-20T10:00:00Z",
};

describe("<HomePage /> dashboard", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    setOwner();
    // KPI tiles + AI insights latest must both return something so the
    // polling/effect chain settles.
    mock.onGet("/api/v1/dashboard/kpis").reply(200, KPI_PAYLOAD);
  });

  afterEach(() => {
    mock.restore();
  });

  it("wires KPI tiles + the empty-insight tile prompt", async () => {
    mock
      .onGet("/api/v1/dashboard/ai-insights/latest")
      .reply(200, null);

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("kpi-tiles")).toBeInTheDocument(),
    );
    expect(screen.getByText("500.00")).toBeInTheDocument();
    expect(screen.getByText("1 overdue")).toBeInTheDocument();
    // GL tiles render as moved-to-QuickBooks placeholders.
    expect(screen.getAllByText("In QuickBooks").length).toBeGreaterThan(0);
    expect(
      screen.getByText(/No insight ready yet/),
    ).toBeInTheDocument();
  });

  it("Refresh button POSTs a new request then re-polls latest", async () => {
    let posted = false;
    mock
      .onPost("/api/v1/dashboard/ai-insights/requests")
      .reply((config) => {
        posted = true;
        const body = JSON.parse(config.data as string);
        expect(body.scope).toBe("sales_trend");
        return [201, { id: "x", status: "queued" }];
      });
    let latestCalls = 0;
    mock
      .onGet("/api/v1/dashboard/ai-insights/latest")
      .reply(() => {
        latestCalls += 1;
        if (latestCalls < 2) {
          return [200, null];
        }
        return [
          200,
          {
            id: "x",
            scope: "sales_trend",
            period_start: "2026-03-01",
            period_end: "2026-05-20",
            payload: {},
            narrative: "Synthetic narrative",
            model: "deterministic:deterministic",
            status: "ready",
            error: null,
            requested_by_user_id: null,
            created_at: "2026-05-20T10:00:00Z",
            updated_at: "2026-05-20T10:00:00Z",
          },
        ];
      });

    renderPage();
    const user = userEvent.setup();
    const button = await screen.findByTestId("ai-insights-refresh");
    await user.click(button);
    await waitFor(() => expect(posted).toBe(true));
    await waitFor(
      () => expect(screen.getByTestId("ai-insights-narrative")).toBeInTheDocument(),
      { timeout: 5_000 },
    );
    expect(screen.getByText("Synthetic narrative")).toBeInTheDocument();
  });
});
