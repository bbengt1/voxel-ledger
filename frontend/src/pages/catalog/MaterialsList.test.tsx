import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { MaterialsListPage } from "@/pages/catalog/MaterialsList";
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

function aMaterial(name = "PLA Red") {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    name,
    brand: "Polymaker",
    material_type: "PLA",
    color: "red",
    density_g_per_cm3: "1.24",
    spool_weight_grams: "1000.00",
    current_cost_per_gram: "20.00",
    total_on_hand: "1000.00",
    per_location_on_hand: {},
    low_stock_threshold_grams: null,
    is_archived: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/catalog/materials"]}>
      <AppProviders>
        <Routes>
          <Route path="/catalog/materials" element={<MaterialsListPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<MaterialsListPage />", () => {
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
    mock.onGet("/api/v1/materials").reply(200, {
      items: [aMaterial()],
      next_cursor: null,
    });
    renderPage();
    // DataTable renders a desktop table + mobile card, so cell text appears twice.
    expect((await screen.findAllByText("PLA Red")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Polymaker").length).toBeGreaterThanOrEqual(1);
  });

  it("debounces search input and re-queries with search param", async () => {
    setOwner();
    mock.onGet("/api/v1/materials").reply((config) => {
      const params = config.params as Record<string, string> | undefined;
      if (params?.["search"] === "red") {
        return [
          200,
          { items: [aMaterial("PLA Red")], next_cursor: null },
        ];
      }
      return [200, { items: [], next_cursor: null }];
    });

    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/search/i), "red");
    await waitFor(
      () => {
        expect(screen.getAllByText("PLA Red").length).toBeGreaterThanOrEqual(1);
      },
      { timeout: 1500 },
    );
  });

  it("toggles the archived filter as a query param", async () => {
    setOwner();
    let observedArchived: string | undefined;
    mock.onGet("/api/v1/materials").reply((config) => {
      const params = config.params as Record<string, string> | undefined;
      observedArchived = params?.["is_archived"];
      return [200, { items: [], next_cursor: null }];
    });
    renderPage();
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText(/status/i), "true");
    await waitFor(() => {
      expect(observedArchived).toBe("true");
    });
  });

  it("hides New material for sales role", async () => {
    setSales();
    mock.onGet("/api/v1/materials").reply(200, { items: [], next_cursor: null });
    renderPage();
    await waitFor(() => {
      expect(
        screen.queryByRole("link", { name: /new material/i }),
      ).not.toBeInTheDocument();
    });
  });
});
