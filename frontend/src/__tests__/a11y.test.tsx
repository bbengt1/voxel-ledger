/**
 * WCAG 2.1 AA automated coverage (Phase 12.3a, #205).
 *
 * Each test renders one of the primary flows, waits for async state
 * to settle, then runs axe-core. WCAG 2.1 AA tag set.
 *
 * Out of scope here: keyboard / VoiceOver pass, color-contrast
 * audit of the Tailwind palette. Tracked in the 12.3b follow-up.
 */
import { render, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { ControlCenterPage } from "@/pages/ControlCenter";
import { HomePage } from "@/pages/Home";
import { LoginPage } from "@/pages/Login";
import { ReportsInQuickBooksPage } from "@/pages/reports/ReportsInQuickBooks";
import { useAuthStore } from "@/store/useAuthStore";
import { expectNoA11yViolations } from "@/test-utils/axe";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderRoute(initial: string, element: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <AppProviders>
        <Routes>
          <Route path={initial} element={element} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("WCAG 2.1 AA — primary flows", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
  });

  it("Login page has no axe violations", async () => {
    const { container, getByRole } = render(
      <MemoryRouter initialEntries={["/login"]}>
        <AppProviders>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
          </Routes>
        </AppProviders>
      </MemoryRouter>,
    );
    await waitFor(() => expect(getByRole("button")).toBeInTheDocument());
    await expectNoA11yViolations(container);
  });

  it("Dashboard home has no axe violations", async () => {
    setOwner();
    mock.onGet("/api/v1/dashboard/kpis").reply(200, {
      as_of: "2026-05-21",
      // GL tiles are null since QBO replace-mode (#318 5d).
      cash_on_hand: null,
      accounts_receivable: "0",
      accounts_payable: "0",
      overdue_invoice_count: 0,
      overdue_bill_count: 0,
      low_stock_alert_count: 0,
      net_income_mtd: null,
      net_income_ytd: null,
      last_updated_at: "2026-05-21T00:00:00Z",
    });
    mock.onGet("/api/v1/dashboard/ai-insights/latest").reply(200, null);

    const { container, getByTestId } = renderRoute("/", <HomePage />);
    await waitFor(() => expect(getByTestId("kpi-tiles")).toBeInTheDocument());
    await expectNoA11yViolations(container);
  });

  it("Control Center has no axe violations", async () => {
    setOwner();
    mock.onGet("/api/v1/control-center").reply(200, {
      as_of: "2026-05-21T00:00:00Z",
      pending_approvals: { count: 0, sample: [] },
      low_stock_alerts: { count: 0, sample: [] },
      overdue_invoices: { count: 0, amount_total: "0", sample: [] },
      overdue_bills: { count: 0, amount_total: "0", sample: [] },
      failed_jobs: { count: 0, sample: [] },
      webhook_dlq: { count: 0, sample: [] },
      ws_health: { moonraker_ws_connected: false, last_event_at: null },
    });
    const { container, getByTestId } = renderRoute(
      "/control-center",
      <ControlCenterPage />,
    );
    await waitFor(() =>
      expect(getByTestId("cc-pending-approvals")).toBeInTheDocument(),
    );
    await expectNoA11yViolations(container);
  });

  it("Reports-in-QuickBooks explainer has no axe violations", async () => {
    setOwner();
    mock.onGet("/api/v1/reports/quickbooks-link").reply(200, {
      url: "https://app.qbo.intuit.com",
    });
    const { container, findByText } = renderRoute(
      "/reports/quickbooks",
      <ReportsInQuickBooksPage />,
    );
    await findByText(/Financial reports live in QuickBooks/i);
    await expectNoA11yViolations(container);
  });
});
