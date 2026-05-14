import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { ProductDetailPage } from "@/pages/catalog/ProductDetail";
import { useAuthStore } from "@/store/useAuthStore";

const PID = "11111111-1111-1111-1111-111111111111";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function aProduct(overrides: Record<string, unknown> = {}) {
  return {
    id: PID,
    sku: "PROD-2026-0001",
    upc: null,
    name: "Widget",
    description: "desc",
    unit_price: "10.00",
    unit_cost_cached: null,
    weight_grams: null,
    category: "widgets",
    is_archived: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/catalog/products/${PID}`]}>
      <AppProviders>
        <Routes>
          <Route
            path="/catalog/products/:id"
            element={<ProductDetailPage />}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<ProductDetailPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/inventory/locations").reply(200, {
      items: [],
      next_cursor: null,
    });
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders product and shows the cost placeholder for null unit_cost_cached", async () => {
    setOwner();
    mock.onGet(`/api/v1/products/${PID}`).reply(200, aProduct());
    mock
      .onGet(`/api/v1/products/${PID}/bom`)
      .reply(200, { items: [], total_cost: null });
    renderPage();
    expect(await screen.findByText("Widget")).toBeInTheDocument();
    expect(screen.getByTestId("unit-cost").textContent).toMatch(/no BOM cost data/i);
  });

  it("saves edits and reflects the price-change response", async () => {
    setOwner();
    mock.onGet(`/api/v1/products/${PID}`).reply(200, aProduct());
    mock
      .onGet(`/api/v1/products/${PID}/bom`)
      .reply(200, { items: [], total_cost: null });
    let sentBody: Record<string, unknown> | undefined;
    mock.onPatch(`/api/v1/products/${PID}`).reply((config) => {
      sentBody = JSON.parse(config.data as string);
      return [
        200,
        aProduct({
          unit_price: (sentBody?.["unit_price"] as string) ?? "10.00",
          name: (sentBody?.["name"] as string) ?? "Widget",
        }),
      ];
    });

    renderPage();
    const user = userEvent.setup();
    await waitFor(() => {
      expect(screen.getByTestId("unit-price-input")).toBeInTheDocument();
    });
    const priceInput = screen.getByTestId("unit-price-input") as HTMLInputElement;
    await user.clear(priceInput);
    await user.type(priceInput, "15.00");
    await user.click(screen.getByTestId("save-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("save-msg").textContent).toBe("Saved.");
    });
    expect(sentBody?.["unit_price"]).toBe("15.00");
    expect(screen.getByTestId("unit-price").textContent).toContain("15.00");
  });

  it("renders the OnHand section with per-location breakdown", async () => {
    setOwner();
    mock.reset();
    mock.onGet("/api/v1/inventory/locations").reply(200, {
      items: [
        {
          id: "loc-1",
          name: "Finished goods",
          code: "FG",
          kind: "finished_goods",
          description: null,
          is_archived: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
      next_cursor: null,
    });
    mock.onGet(`/api/v1/products/${PID}`).reply(200, {
      ...aProduct({
        total_on_hand: "7",
        per_location_on_hand: { "loc-1": "7" },
      }),
    });
    mock
      .onGet(`/api/v1/products/${PID}/bom`)
      .reply(200, { items: [], total_cost: null });
    renderPage();
    expect(await screen.findByTestId("on-hand-total")).toHaveTextContent("7");
    await waitFor(() => {
      expect(screen.getByTestId("onhand-per-location")).toHaveTextContent(
        "Finished goods",
      );
    });
  });
});
