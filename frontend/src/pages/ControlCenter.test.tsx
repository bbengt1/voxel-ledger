import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { ControlCenterPage } from "@/pages/ControlCenter";
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
    <MemoryRouter initialEntries={["/control-center"]}>
      <AppProviders>
        <Routes>
          <Route path="/control-center" element={<ControlCenterPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

const EMPTY_PAYLOAD = {
  as_of: "2026-05-21T00:00:00Z",
  pending_approvals: { count: 0, sample: [] },
  low_stock_alerts: { count: 0, sample: [] },
  overdue_invoices: { count: 0, amount_total: "0", sample: [] },
  overdue_bills: { count: 0, amount_total: "0", sample: [] },
  failed_jobs: { count: 0, sample: [] },
  webhook_dlq: { count: 0, sample: [] },
  ws_health: { moonraker_ws_connected: false, last_event_at: null },
};

describe("<ControlCenterPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    mock = new MockAdapter(apiClient);
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders every card on an empty install", async () => {
    mock.onGet("/api/v1/control-center").reply(200, EMPTY_PAYLOAD);
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("cc-pending-approvals")).toBeInTheDocument(),
    );
    for (const id of [
      "cc-low-stock",
      "cc-overdue-invoices",
      "cc-overdue-bills",
      "cc-failed-jobs",
      "cc-webhook-dlq",
    ]) {
      expect(screen.getByTestId(id)).toBeInTheDocument();
    }
    expect(screen.getByTestId("cc-ws-status").textContent).toMatch(/not connected/);
  });

  it("renders counts and amount totals when populated", async () => {
    mock.onGet("/api/v1/control-center").reply(200, {
      ...EMPTY_PAYLOAD,
      overdue_invoices: {
        count: 2,
        amount_total: "125.00",
        sample: [{ id: "1", invoice_number: "INV-1", amount_outstanding: "100" }],
      },
    });
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("cc-overdue-invoices")).toHaveTextContent("2"),
    );
    expect(screen.getByTestId("cc-overdue-invoices")).toHaveTextContent("125.00");
  });
});
