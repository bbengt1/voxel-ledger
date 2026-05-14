import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { StartingBalancesPage } from "@/pages/inventory/StartingBalances";
import { useAuthStore, type Role } from "@/store/useAuthStore";

function setRole(role: Role) {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "e@e", role },
  });
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/inventory/starting-balances"]}>
      <AppProviders>
        <Routes>
          <Route
            path="/inventory/starting-balances"
            element={<StartingBalancesPage />}
          />
          <Route path="/" element={<div data-testid="home">home</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

const LOC = {
  id: "loc-1",
  name: "Workshop",
  code: "WSB",
  kind: "workshop",
  description: null,
  is_archived: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("<StartingBalancesPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    mock = new MockAdapter(apiClient);
    mock
      .onGet("/api/v1/inventory/locations")
      .reply(200, { items: [LOC], next_cursor: null });
    mock.onGet("/api/v1/materials").reply(200, {
      items: [{ id: "mat-1", name: "PLA Black" }],
      next_cursor: null,
    });
  });
  afterEach(() => {
    mock.restore();
  });

  it("redirects non-write roles to /", async () => {
    setRole("viewer");
    renderPage();
    expect(await screen.findByTestId("home")).toBeInTheDocument();
  });

  it("submits a single starting balance as an adjustment", async () => {
    setRole("owner");
    let observed: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/inventory/transactions").reply((cfg) => {
      observed = JSON.parse(cfg.data as string);
      return [201, { id: "tx-1" }];
    });
    renderPage();
    const user = userEvent.setup();
    // Pick entity via the autocomplete
    await user.click(
      (await screen.findByTestId("single-entity")).querySelector(
        "input",
      ) as HTMLElement,
    );
    await user.click(await screen.findByText("PLA Black"));
    await user.selectOptions(screen.getByTestId("single-location"), "loc-1");
    await user.type(screen.getByTestId("single-quantity"), "42");
    await user.click(screen.getByTestId("single-submit"));
    await waitFor(() => {
      expect(observed).toMatchObject({
        kind: "adjustment",
        reason: "initial balance",
        quantity: "42",
        entity_id: "mat-1",
        location_id: "loc-1",
      });
    });
    expect(await screen.findByTestId("single-msg")).toBeInTheDocument();
  });
});
