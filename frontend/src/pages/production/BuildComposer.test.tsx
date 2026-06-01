import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { BuildComposerPage } from "@/pages/production/BuildComposer";
import { useAuthStore } from "@/store/useAuthStore";

function setProduction() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "p@example.com", role: "production" },
  });
}

const PRODUCT_ID = "11111111-1111-1111-1111-111111111111";
const PART_ID = "22222222-2222-2222-2222-222222222222";
const SUPPLY_ID = "33333333-3333-3333-3333-333333333333";

const PRODUCT = {
  id: PRODUCT_ID,
  name: "Widget",
  sku: "W-1",
  unit_price: "25.00",
  is_archived: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  description: null,
  category: null,
  upc: null,
  low_stock_threshold: null,
  weight_grams: null,
  assembly_minutes: 5,
  custom_fields: null,
};

const PLAN = {
  product_id: PRODUCT_ID,
  quantity: 2,
  assembly_minutes: 10,
  location_id: "44444444-4444-4444-4444-444444444444",
  lines: [
    {
      component_kind: "part",
      component_id: PART_ID,
      name: "Bracket (P-1)",
      quantity_per_product: "1",
      required_quantity: "2",
      on_hand: "5",
      sufficient: true,
      unit_cost: "1.50",
      line_cost: "3.00",
    },
    {
      component_kind: "supply",
      component_id: SUPPLY_ID,
      name: "M3 screw",
      quantity_per_product: "2",
      required_quantity: "4",
      on_hand: "1",
      sufficient: false,
      unit_cost: "0.10",
      line_cost: "0.40",
    },
  ],
  component_cost: "3.40",
  assembly_labor_cost: "0.50",
  unit_cost: "1.95",
  total_cost: "3.90",
  can_build: false,
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/production/builds/new"]}>
      <AppProviders>
        <Routes>
          <Route path="/production/builds/new" element={<BuildComposerPage />} />
          <Route path="/production/builds/:id" element={<div>build-detail</div>} />
          <Route path="/production/builds" element={<div>builds-list</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<BuildComposerPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/products").reply(200, { items: [PRODUCT], next_cursor: null });
    setProduction();
  });

  afterEach(() => {
    mock.restore();
    vi.useRealTimers();
  });

  async function pickProduct(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByTestId("build-product-picker-input"));
    await waitFor(() => {
      expect(
        screen.getByTestId(`build-product-picker-option-${PRODUCT_ID}`),
      ).toBeInTheDocument();
    });
    await user.click(screen.getByTestId(`build-product-picker-option-${PRODUCT_ID}`));
  }

  it("debounces the preview and renders availability + cost", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    const calls: unknown[] = [];
    mock.onPost("/api/v1/builds/preview").reply((config) => {
      calls.push(JSON.parse(config.data as string));
      return [200, PLAN];
    });

    renderPage();
    await pickProduct(user);
    await user.clear(screen.getByTestId("build-qty-input"));
    await user.type(screen.getByTestId("build-qty-input"), "2");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(350);
    });

    await waitFor(() => {
      expect(screen.getByTestId("plan-total-cost")).toHaveTextContent("$3.90");
    });
    // Short supply line flagged; not buildable.
    expect(screen.getByTestId("plan-can-build")).toHaveTextContent("Insufficient stock");
    expect(screen.getByTestId(`plan-onhand-${SUPPLY_ID}`)).toHaveTextContent("1");
    expect(calls.length).toBeGreaterThanOrEqual(1);
    const last = calls[calls.length - 1] as { product_id: string; quantity: number };
    expect(last.product_id).toBe(PRODUCT_ID);
    expect(last.quantity).toBe(2);
  });

  it("creates a draft build and navigates to its detail page", async () => {
    const user = userEvent.setup();
    mock.onPost("/api/v1/builds/preview").reply(200, PLAN);
    mock.onPost("/api/v1/builds").reply((config) => {
      const body = JSON.parse(config.data as string);
      expect(body.product_id).toBe(PRODUCT_ID);
      expect(body.quantity).toBe(2);
      return [
        201,
        {
          id: "55555555-5555-5555-5555-555555555555",
          build_number: "BUILD-2026-0001",
          product_id: PRODUCT_ID,
          state: "draft",
          quantity: 2,
          assembly_minutes: 10,
          location_id: null,
          unit_cost_cached: null,
          total_cost_cached: null,
          notes: null,
          actor_user_id: "u",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ];
    });

    renderPage();
    await pickProduct(user);
    await user.clear(screen.getByTestId("build-qty-input"));
    await user.type(screen.getByTestId("build-qty-input"), "2");
    await user.click(screen.getByTestId("create-build-btn"));

    await waitFor(() => {
      expect(screen.getByText("build-detail")).toBeInTheDocument();
    });
  });
});
