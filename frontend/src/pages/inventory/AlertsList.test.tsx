import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { AlertsListPage } from "@/pages/inventory/AlertsList";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "e@e", role: "owner" },
  });
}

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/inventory/alerts"]}>
      <AppProviders>
        <Routes>
          <Route path="/inventory/alerts" element={<AlertsListPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<AlertsListPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    setOwner();
    mock = new MockAdapter(apiClient);
    mock
      .onGet("/api/v1/inventory/locations")
      .reply(200, { items: [], next_cursor: null });
  });
  afterEach(() => {
    mock.restore();
  });

  it("renders rows from the alerts endpoint", async () => {
    mock.onGet("/api/v1/inventory/alerts/low-stock").reply(200, {
      items: [
        {
          entity_kind: "material",
          entity_id: "m-1",
          entity_name: "PLA",
          threshold: "500",
          total_on_hand: "100",
          deficit: "400",
        },
      ],
    });
    renderPage();
    expect(await screen.findByTestId("alert-row-m-1")).toHaveTextContent(
      "PLA",
    );
  });

  it("renders the empty state when no alerts come back", async () => {
    mock
      .onGet("/api/v1/inventory/alerts/low-stock")
      .reply(200, { items: [] });
    renderPage();
    expect(await screen.findByTestId("alerts-empty")).toHaveTextContent(
      "All stocked up",
    );
  });

  it("passes the entity_kind filter to the API", async () => {
    const params: Array<Record<string, unknown>> = [];
    mock.onGet("/api/v1/inventory/alerts/low-stock").reply((cfg) => {
      params.push((cfg.params ?? {}) as Record<string, unknown>);
      return [200, { items: [] }];
    });
    renderPage();
    await screen.findByTestId("alerts-empty");
    await userEvent.selectOptions(
      screen.getByTestId("alerts-filter-kind"),
      "material",
    );
    await waitFor(() =>
      expect(params.some((p) => p["entity_kind"] === "material")).toBe(true),
    );
  });
});
