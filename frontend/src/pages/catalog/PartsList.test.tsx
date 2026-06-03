import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { PartsListPage } from "@/pages/catalog/PartsList";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function aPart(overrides: Record<string, unknown> = {}) {
  return {
    id: "22222222-2222-2222-2222-222222222222",
    sku: "PART-2026-0001",
    name: "Bracket",
    description: null,
    print_minutes: 90,
    setup_minutes: 5,
    parts_per_run: 4,
    print_grams_by_material: {},
    assigned_printer_ids: [],
    unit_cost_cached: null,
    total_on_hand: "0",
    is_archived: false,
    custom_fields: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/catalog/parts"]}>
      <AppProviders>
        <Routes>
          <Route path="/catalog/parts" element={<PartsListPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<PartsListPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    mock = new MockAdapter(apiClient);
    setOwner();
    // Per-user column preference fetch (useColumnVisibility).
    mock.onGet(/\/api\/v1\/me\/preferences\//).reply(200, {
      key: "table_columns.parts",
      value: {},
    });
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders parts with cost placeholder and the New part button", async () => {
    mock.onGet("/api/v1/parts").reply(200, { items: [aPart()], next_cursor: null });
    renderPage();
    // DataTable renders a desktop table + mobile card, so cell text appears twice.
    expect((await screen.findAllByText("Bracket")).length).toBeGreaterThanOrEqual(1);
    // Cost shows "—" until Phase 2 populates unit_cost_cached.
    expect(
      screen.getAllByTestId("part-cost-22222222-2222-2222-2222-222222222222")[0],
    ).toHaveTextContent("—");
    expect(screen.getByRole("link", { name: /new part/i })).toHaveAttribute(
      "href",
      "/catalog/parts/new",
    );
  });

  it("shows each part's on-hand quantity", async () => {
    mock.onGet("/api/v1/parts").reply(200, {
      items: [aPart({ total_on_hand: "12" })],
      next_cursor: null,
    });
    renderPage();
    await screen.findAllByText("Bracket");
    expect(
      screen.getAllByTestId("part-onhand-22222222-2222-2222-2222-222222222222")[0],
    ).toHaveTextContent("12");
  });

  it("shows the empty state when no parts match", async () => {
    mock.onGet("/api/v1/parts").reply(200, { items: [], next_cursor: null });
    renderPage();
    await waitFor(() =>
      expect(screen.getAllByText(/no parts match/i).length).toBeGreaterThanOrEqual(1),
    );
  });
});
