import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { ProductsListPage } from "@/pages/catalog/ProductsList";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function setViewer() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "v@example.com", role: "viewer" },
  });
}

function aProduct(overrides: Record<string, unknown> = {}) {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    sku: "PROD-2026-0001",
    upc: null,
    name: "Widget A",
    description: null,
    unit_price: "9.99",
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
    <MemoryRouter initialEntries={["/catalog/products"]}>
      <AppProviders>
        <Routes>
          <Route path="/catalog/products" element={<ProductsListPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<ProductsListPage />", () => {
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
    mock.onGet("/api/v1/products").reply(200, {
      items: [aProduct()],
      next_cursor: null,
    });
    renderPage();
    expect(await screen.findByText("Widget A")).toBeInTheDocument();
    expect(screen.getByText("PROD-2026-0001")).toBeInTheDocument();
  });

  it("debounces search input and forwards the search param", async () => {
    setOwner();
    mock.onGet("/api/v1/products").reply((config) => {
      const params = config.params as Record<string, string> | undefined;
      if (params?.["search"] === "widget") {
        return [200, { items: [aProduct({ name: "Widget Match" })], next_cursor: null }];
      }
      return [200, { items: [], next_cursor: null }];
    });

    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/search/i), "widget");
    await waitFor(
      () => {
        expect(screen.getByText("Widget Match")).toBeInTheDocument();
      },
      { timeout: 1500 },
    );
  });

  it("forwards a category filter", async () => {
    setOwner();
    let observed: string | undefined;
    mock.onGet("/api/v1/products").reply((config) => {
      const params = config.params as Record<string, string> | undefined;
      observed = params?.["category"];
      return [200, { items: [], next_cursor: null }];
    });
    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/category/i), "widgets");
    await waitFor(() => {
      expect(observed).toBe("widgets");
    });
  });

  it("hides New product for viewer role", async () => {
    setViewer();
    mock.onGet("/api/v1/products").reply(200, { items: [], next_cursor: null });
    renderPage();
    await waitFor(() => {
      expect(
        screen.queryByRole("link", { name: /new product/i }),
      ).not.toBeInTheDocument();
    });
  });
});
