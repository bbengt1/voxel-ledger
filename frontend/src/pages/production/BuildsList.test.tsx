import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { BuildsListPage } from "@/pages/production/BuildsList";
import { useAuthStore } from "@/store/useAuthStore";

function setProduction() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "p@example.com", role: "production" },
  });
}

const BUILD_ID = "55555555-5555-5555-5555-555555555555";

function renderPage(initial = "/production/builds") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <AppProviders>
        <Routes>
          <Route path="/production/builds" element={<BuildsListPage />} />
          <Route path="/production/builds/new" element={<div>composer</div>} />
          <Route path="/production/builds/:id" element={<div>build-detail</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<BuildsListPage />", () => {
  let mock: MockAdapter;
  let lastParams: Record<string, string> | undefined;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/builds").reply((config) => {
      lastParams = config.params as Record<string, string>;
      return [
        200,
        {
          items: [
            {
              id: BUILD_ID,
              build_number: "BUILD-2026-0001",
              product_id: "p",
              state: lastParams?.state ?? "draft",
              quantity: 3,
              assembly_minutes: 10,
              location_id: null,
              unit_cost_cached: "1.75",
              total_cost_cached: "5.25",
              notes: null,
              actor_user_id: "u",
              created_at: "2026-01-01T00:00:00Z",
              updated_at: "2026-01-01T00:00:00Z",
            },
          ],
          next_cursor: null,
        },
      ];
    });
    setProduction();
  });

  afterEach(() => {
    mock.restore();
  });

  it("lists builds and shows the New build button", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText("BUILD-2026-0001").length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText("$5.25").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "New build" })).toBeInTheDocument();
  });

  it("passes the state filter to the API", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText("BUILD-2026-0001").length).toBeGreaterThan(0);
    });
    await user.selectOptions(screen.getByTestId("build-filter-state"), "completed");
    await waitFor(() => {
      expect(lastParams?.["state"]).toBe("completed");
    });
  });
});
