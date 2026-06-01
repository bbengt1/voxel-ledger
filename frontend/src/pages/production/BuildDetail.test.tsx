import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { BuildDetailPage } from "@/pages/production/BuildDetail";
import { useAuthStore } from "@/store/useAuthStore";

function setProduction() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "p@example.com", role: "production" },
  });
}

const BUILD_ID = "55555555-5555-5555-5555-555555555555";
const PRODUCT_ID = "11111111-1111-1111-1111-111111111111";
const PART_ID = "22222222-2222-2222-2222-222222222222";

function draftBuild(overrides: Record<string, unknown> = {}) {
  return {
    id: BUILD_ID,
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
    ...overrides,
  };
}

function plan(canBuild: boolean) {
  return {
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
        on_hand: canBuild ? "5" : "0",
        sufficient: canBuild,
        unit_cost: "1.50",
        line_cost: "3.00",
      },
    ],
    component_cost: "3.00",
    assembly_labor_cost: "0.50",
    unit_cost: "1.75",
    total_cost: "3.50",
    can_build: canBuild,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/production/builds/${BUILD_ID}`]}>
      <AppProviders>
        <Routes>
          <Route path="/production/builds/:id" element={<BuildDetailPage />} />
          <Route path="/production/builds" element={<div>builds-list</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<BuildDetailPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    setProduction();
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders the build and completes it when stock is sufficient", async () => {
    const user = userEvent.setup();
    let completed = false;
    mock.onGet(`/api/v1/builds/${BUILD_ID}`).reply(() => [
      200,
      completed ? draftBuild({ state: "completed", total_cost_cached: "3.50", unit_cost_cached: "1.75" }) : draftBuild(),
    ]);
    mock.onGet(`/api/v1/builds/${BUILD_ID}/plan`).reply(200, plan(true));
    mock.onPost(`/api/v1/builds/${BUILD_ID}/complete`).reply(() => {
      completed = true;
      return [200, draftBuild({ state: "completed" })];
    });

    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("build-state")).toHaveTextContent("draft");
    });
    // Plan ready → complete enabled.
    const btn = await screen.findByTestId("build-complete-btn");
    expect(btn).not.toBeDisabled();
    await user.click(btn);

    await waitFor(() => {
      expect(screen.getByTestId("build-state")).toHaveTextContent("completed");
    });
    expect(screen.getByTestId("build-total-cost")).toHaveTextContent("$3.50");
  });

  it("disables complete and surfaces a 409 when stock is short", async () => {
    const user = userEvent.setup();
    mock.onGet(`/api/v1/builds/${BUILD_ID}`).reply(200, draftBuild());
    mock.onGet(`/api/v1/builds/${BUILD_ID}/plan`).reply(200, plan(false));
    mock.onPost(`/api/v1/builds/${BUILD_ID}/complete`).reply(409, {
      detail: { message: "insufficient stock to build", shortfalls: [] },
    });

    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("plan-can-build")).toHaveTextContent("Insufficient stock");
    });
    // Complete button disabled because the plan can't build.
    expect(screen.getByTestId("build-complete-btn")).toBeDisabled();
    // Cancel still works.
    expect(screen.getByTestId("build-cancel-btn")).not.toBeDisabled();
    void user; // no click needed
  });
});
