import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { ProductCreatePage } from "@/pages/catalog/ProductCreate";
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
    <MemoryRouter initialEntries={["/catalog/products/new"]}>
      <AppProviders>
        <Routes>
          <Route path="/catalog/products/new" element={<ProductCreatePage />} />
          <Route
            path="/catalog/products/:id"
            element={<div data-testid="redirected">redirected</div>}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<ProductCreatePage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
  });

  it("submits without a SKU and lets the server auto-generate", async () => {
    setOwner();
    let sentBody: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/products").reply((config) => {
      sentBody = JSON.parse(config.data as string);
      return [
        201,
        {
          id: "p1",
          sku: "PROD-2026-0001",
          upc: null,
          name: sentBody?.["name"],
          description: null,
          unit_price: "9.99",
          unit_cost_cached: null,
          weight_grams: null,
          category: null,
          is_archived: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ];
    });
    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/^name$/i), "Widget A");
    await user.type(screen.getByLabelText(/^unit price$/i), "9.99");
    await user.click(screen.getByRole("button", { name: /create product/i }));
    await waitFor(() => {
      expect(screen.getByTestId("redirected")).toBeInTheDocument();
    });
    expect(sentBody).toBeDefined();
    expect(sentBody).not.toHaveProperty("sku");
    expect(sentBody?.["name"]).toBe("Widget A");
    expect(sentBody?.["unit_price"]).toBe("9.99");
  });

  it("submits a manual SKU when the user provides one", async () => {
    setOwner();
    let sentBody: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/products").reply((config) => {
      sentBody = JSON.parse(config.data as string);
      return [
        201,
        {
          id: "p2",
          sku: sentBody?.["sku"] ?? "PROD-2026-0001",
          upc: null,
          name: sentBody?.["name"],
          description: null,
          unit_price: "1.00",
          unit_cost_cached: null,
          weight_grams: null,
          category: null,
          is_archived: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ];
    });
    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByTestId("sku-input"), "CUSTOM-001");
    await user.type(screen.getByLabelText(/^name$/i), "Widget B");
    await user.type(screen.getByLabelText(/^unit price$/i), "1.00");
    await user.click(screen.getByRole("button", { name: /create product/i }));
    await waitFor(() => {
      expect(screen.getByTestId("redirected")).toBeInTheDocument();
    });
    expect(sentBody?.["sku"]).toBe("CUSTOM-001");
  });

  it("shows the auto-generate hint", () => {
    setOwner();
    renderPage();
    expect(screen.getByText(/auto-generate as prod-yyyy-nnnn/i)).toBeInTheDocument();
  });
});
