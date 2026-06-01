import { render, screen } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { PartDetailPage } from "@/pages/catalog/PartDetail";
import { useAuthStore } from "@/store/useAuthStore";

const PID = "22222222-2222-2222-2222-222222222222";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function aPart(overrides: Record<string, unknown> = {}) {
  return {
    id: PID,
    sku: "PART-2026-0001",
    name: "Bracket",
    description: null,
    print_minutes: 60,
    setup_minutes: 5,
    parts_per_run: 1,
    print_grams_by_material: {},
    assigned_printer_ids: [],
    unit_cost_cached: "6.33",
    is_archived: false,
    custom_fields: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function aCost() {
  return {
    pieces_per_set: 1,
    sets_required: 1,
    material_cost: "2.00",
    supply_cost: "0.00",
    labor_cost: "1.00",
    machine_cost: "3.00",
    overhead_cost: "0.33",
    total_cost: "6.33",
    cost_per_piece: "6.33",
    suggested_unit_price: "8.23",
    electricity_cost: "0.00",
    preheat_cost: "0.00",
    depreciation_cost: "0.00",
    failure_adjustment_cost: "0.00",
    per_plate: [],
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/catalog/parts/${PID}`]}>
      <AppProviders>
        <Routes>
          <Route path="/catalog/parts/:id" element={<PartDetailPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<PartDetailPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    mock = new MockAdapter(apiClient);
    setOwner();
    mock.onGet(`/api/v1/parts/${PID}/cost`).reply(200, aCost());
    mock.onGet(`/api/v1/parts/${PID}/image`).reply(404);
    mock.onGet(`/api/v1/parts/${PID}`).reply(200, aPart());
    mock.onGet("/api/v1/materials").reply(200, { items: [] });
    mock.onGet("/api/v1/printers").reply(200, { items: [] });
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders the live cost breakdown from /parts/{id}/cost", async () => {
    renderPage();
    expect(await screen.findByText("Bracket")).toBeInTheDocument();
    const panel = await screen.findByTestId("live-cost-panel");
    expect(panel).toBeInTheDocument();
    expect(await screen.findByTestId("cost-total")).toHaveTextContent("6.33");
    expect(screen.getByTestId("cost-per-piece")).toHaveTextContent("6.33");
  });
});
