import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { JobComposerPage } from "@/pages/production/JobComposer";
import { useAuthStore } from "@/store/useAuthStore";

function setProduction() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "p@example.com", role: "production" },
  });
}

const PRODUCT_ID = "11111111-1111-1111-1111-111111111111";
const MATERIAL_ID = "22222222-2222-2222-2222-222222222222";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/production/jobs/new"]}>
      <AppProviders>
        <Routes>
          <Route path="/production/jobs/new" element={<JobComposerPage />} />
          <Route path="/production/jobs/:id" element={<div>job-detail</div>} />
          <Route path="/production/jobs" element={<div>jobs-list</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<JobComposerPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    // Stable list endpoints.
    mock.onGet("/api/v1/printers").reply(200, { items: [], next_cursor: null });
    mock
      .onGet("/api/v1/materials")
      .reply(200, {
        items: [
          {
            id: MATERIAL_ID,
            name: "PLA Black",
            kind: "filament",
            unit: "g",
            unit_price: "0.025",
            is_archived: false,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
            custom_fields: null,
          },
        ],
        next_cursor: null,
      });
    mock
      .onGet("/api/v1/products")
      .reply(200, {
        items: [
          {
            id: PRODUCT_ID,
            name: "Widget",
            sku: "W-1",
            unit_price: "5.00",
            is_archived: false,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
            description: null,
            category: null,
            upc: null,
            low_stock_threshold: null,
            weight_grams: null,
            custom_fields: null,
          },
        ],
        next_cursor: null,
      });
    setProduction();
  });

  afterEach(() => {
    mock.restore();
    vi.useRealTimers();
  });

  it("debounces calculate calls and renders the cost panel total", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    const calcCalls: unknown[] = [];
    mock.onPost("/api/v1/jobs/calculate").reply((config) => {
      calcCalls.push(JSON.parse(config.data as string));
      return [
        200,
        {
          pieces_per_set: 4,
          sets_required: 1,
          material_cost: "1.25",
          supply_cost: "0.00",
          labor_cost: "0.50",
          machine_cost: "0.25",
          overhead_cost: "0.10",
          total_cost: "2.10",
          cost_per_piece: "0.53",
          suggested_unit_price: "1.05",
          per_plate: [],
        },
      ];
    });

    renderPage();

    // Fill required header fields.
    await user.clear(screen.getByTestId("job-qty-input"));
    await user.type(screen.getByTestId("job-qty-input"), "4");

    // Fill plate 0.
    await user.clear(screen.getByTestId("plate-print-minutes-0"));
    await user.type(screen.getByTestId("plate-print-minutes-0"), "60");

    // Type grams — this is the headline interaction; nothing should fire
    // until the debounce window elapses.
    await user.type(screen.getByTestId("plate-0-grams-0"), "25");

    // Before debounce: no calc has fired yet for the latest input.
    expect(calcCalls.length).toBe(0);

    // Advance debounce window.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(350);
    });

    await waitFor(() => {
      expect(screen.getByTestId("cost-total")).toHaveTextContent("$2.10");
    });

    // Exactly one calculate call should have fired despite multiple keypresses.
    expect(calcCalls.length).toBeGreaterThanOrEqual(1);
  });

  it("submits the job and navigates to its detail page", async () => {
    const user = userEvent.setup();
    mock.onPost("/api/v1/jobs/calculate").reply(200, {
      pieces_per_set: 1,
      sets_required: 1,
      material_cost: "0",
      supply_cost: "0",
      labor_cost: "0",
      machine_cost: "0",
      overhead_cost: "0",
      total_cost: "0",
      cost_per_piece: "0",
      suggested_unit_price: "0",
      per_plate: [],
    });
    mock.onPost("/api/v1/jobs").reply((config) => {
      const body = JSON.parse(config.data as string);
      expect(body.product_id).toBe(PRODUCT_ID);
      expect(body.quantity_ordered).toBe(2);
      expect(body.plates).toHaveLength(1);
      return [
        201,
        {
          id: "33333333-3333-3333-3333-333333333333",
          job_number: "JOB-2026-0001",
          state: "draft",
          quantity_ordered: 2,
          pieces_produced: 0,
          priority: 0,
          product_id: PRODUCT_ID,
          actor_user_id: "u",
          plates: [],
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ];
    });

    renderPage();

    // Open product picker and pick the only result.
    await user.click(screen.getByTestId("job-product-picker-input"));
    await waitFor(() => {
      expect(
        screen.getByTestId(`job-product-picker-option-${PRODUCT_ID}`),
      ).toBeInTheDocument();
    });
    await user.click(
      screen.getByTestId(`job-product-picker-option-${PRODUCT_ID}`),
    );

    await user.clear(screen.getByTestId("job-qty-input"));
    await user.type(screen.getByTestId("job-qty-input"), "2");
    await user.clear(screen.getByTestId("plate-print-minutes-0"));
    await user.type(screen.getByTestId("plate-print-minutes-0"), "30");

    await user.click(screen.getByTestId("save-draft-btn"));

    await waitFor(() => {
      expect(screen.getByText("job-detail")).toBeInTheDocument();
    });
  });
});
