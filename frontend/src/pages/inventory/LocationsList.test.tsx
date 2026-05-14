import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { LocationsListPage } from "@/pages/inventory/LocationsList";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function setSales() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "s@example.com", role: "sales" },
  });
}

function aLocation(
  overrides: Partial<{
    id: string;
    name: string;
    code: string;
    kind: string;
    is_archived: boolean;
  }> = {},
) {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    name: "Workshop bench",
    code: "WSB",
    kind: "workshop",
    description: null,
    is_archived: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/inventory/locations"]}>
      <AppProviders>
        <Routes>
          <Route path="/inventory/locations" element={<LocationsListPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<LocationsListPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders rows from the API", async () => {
    setOwner();
    mock.onGet("/api/v1/inventory/locations").reply(200, {
      items: [aLocation()],
      next_cursor: null,
    });
    renderPage();
    expect(await screen.findByText("Workshop bench")).toBeInTheDocument();
    expect(screen.getByText("WSB")).toBeInTheDocument();
    expect(screen.getByText("workshop")).toBeInTheDocument();
  });

  it("hides New location for sales role", async () => {
    setSales();
    mock
      .onGet("/api/v1/inventory/locations")
      .reply(200, { items: [], next_cursor: null });
    renderPage();
    await waitFor(() => {
      expect(
        screen.queryByRole("link", { name: /new location/i }),
      ).not.toBeInTheDocument();
    });
  });

  it("passes kind filter to the API", async () => {
    setOwner();
    const calls: string[] = [];
    mock.onGet("/api/v1/inventory/locations").reply((config) => {
      const url =
        (config.url ?? "") +
        "?" +
        new URLSearchParams(
          (config.params ?? {}) as Record<string, string>,
        ).toString();
      calls.push(url);
      return [200, { items: [], next_cursor: null }];
    });
    renderPage();
    await screen.findByText(/no locations match/i);
    await userEvent.selectOptions(
      screen.getByLabelText(/^Kind$/i),
      "finished_goods",
    );
    await waitFor(() => {
      expect(calls.some((u) => u.includes("kind=finished_goods"))).toBe(true);
    });
  });

  it("passes archived filter to the API", async () => {
    setOwner();
    const calls: string[] = [];
    mock.onGet("/api/v1/inventory/locations").reply((config) => {
      const url =
        (config.url ?? "") +
        "?" +
        new URLSearchParams(
          (config.params ?? {}) as Record<string, string>,
        ).toString();
      calls.push(url);
      return [200, { items: [], next_cursor: null }];
    });
    renderPage();
    await screen.findByText(/no locations match/i);
    await userEvent.selectOptions(screen.getByLabelText(/^Status$/i), "true");
    await waitFor(() => {
      expect(calls.some((u) => u.includes("is_archived=true"))).toBe(true);
    });
  });
});
