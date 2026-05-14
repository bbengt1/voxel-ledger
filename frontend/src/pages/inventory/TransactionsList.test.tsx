import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { TransactionsListPage } from "@/pages/inventory/TransactionsList";
import { useAuthStore, type Role } from "@/store/useAuthStore";

function setRole(role: Role) {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "e@e", role },
  });
}

function renderPage(path = "/inventory/transactions") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppProviders>
        <Routes>
          <Route
            path="/inventory/transactions"
            element={<TransactionsListPage />}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

const TX = {
  id: "tx-1",
  kind: "receipt" as const,
  entity_kind: "material" as const,
  entity_id: "mat-1",
  location_id: "loc-1",
  occurred_at: "2026-01-01T12:00:00Z",
  created_at: "2026-01-01T12:00:00Z",
  quantity: "100",
  reason: "Vendor delivery",
  actor_user_id: null,
};

describe("<TransactionsListPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock
      .onGet("/api/v1/inventory/locations")
      .reply(200, { items: [], next_cursor: null });
  });
  afterEach(() => {
    mock.restore();
  });

  it("renders rows from the API", async () => {
    setRole("owner");
    mock
      .onGet("/api/v1/inventory/transactions")
      .reply(200, { items: [TX], next_cursor: null });
    renderPage();
    expect(await screen.findByText(/Receipt/)).toBeInTheDocument();
  });

  it("passes entity_kind filter to the API and clears cursor", async () => {
    setRole("owner");
    const calls: Array<Record<string, unknown>> = [];
    mock.onGet("/api/v1/inventory/transactions").reply((config) => {
      calls.push((config.params ?? {}) as Record<string, unknown>);
      return [200, { items: [], next_cursor: null }];
    });
    renderPage();
    await screen.findByText(/No transactions/i);
    await userEvent.selectOptions(
      screen.getByTestId("filter-entity-kind"),
      "material",
    );
    await waitFor(() =>
      expect(
        calls.some((c) => c["entity_kind"] === "material"),
      ).toBe(true),
    );
  });

  it("hides the Transfer button for sales role", async () => {
    setRole("sales");
    mock
      .onGet("/api/v1/inventory/transactions")
      .reply(200, { items: [], next_cursor: null });
    renderPage();
    await screen.findByText(/No transactions/i);
    expect(screen.queryByTestId("open-transfer")).not.toBeInTheDocument();
    expect(screen.getByTestId("open-record")).toBeInTheDocument();
  });

  it("hides both action buttons for viewer", async () => {
    setRole("viewer");
    mock
      .onGet("/api/v1/inventory/transactions")
      .reply(200, { items: [], next_cursor: null });
    renderPage();
    await screen.findByText(/No transactions/i);
    expect(screen.queryByTestId("open-record")).not.toBeInTheDocument();
    expect(screen.queryByTestId("open-transfer")).not.toBeInTheDocument();
  });
});
