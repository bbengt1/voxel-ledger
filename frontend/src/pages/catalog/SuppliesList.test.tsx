import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { SuppliesListPage } from "@/pages/catalog/SuppliesList";
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

function aSupply(name = "Bubble Wrap") {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    name,
    unit: "m",
    unit_cost: "0.250000",
    vendor: "ULINE",
    total_on_hand: "100.000000",
    per_location_on_hand: {},
    low_stock_threshold: null,
    is_archived: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/catalog/supplies"]}>
      <AppProviders>
        <Routes>
          <Route path="/catalog/supplies" element={<SuppliesListPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<SuppliesListPage />", () => {
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
    mock.onGet("/api/v1/supplies").reply(200, {
      items: [aSupply()],
      next_cursor: null,
    });
    renderPage();
    expect(await screen.findByText("Bubble Wrap")).toBeInTheDocument();
    expect(screen.getByText("ULINE")).toBeInTheDocument();
  });

  it("hides New supply for sales role", async () => {
    setSales();
    mock.onGet("/api/v1/supplies").reply(200, { items: [], next_cursor: null });
    renderPage();
    await waitFor(() => {
      expect(
        screen.queryByRole("link", { name: /new supply/i }),
      ).not.toBeInTheDocument();
    });
  });
});
