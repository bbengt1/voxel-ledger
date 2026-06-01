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

const PART_ID = "11111111-1111-1111-1111-111111111111";
const MATERIAL_ID = "22222222-2222-2222-2222-222222222222";

const PART = {
  id: PART_ID,
  name: "Bracket",
  sku: "P-1",
  description: null,
  parts_per_run: 4,
  print_minutes: 60,
  setup_minutes: 10,
  print_grams_by_material: { [MATERIAL_ID]: "25" },
  assigned_printer_ids: [],
  unit_cost_cached: "1.50",
  is_archived: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  custom_fields: null,
};

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
      .onGet("/api/v1/parts")
      .reply(200, { items: [PART], next_cursor: null });
    mock.onGet(`/api/v1/parts/${PART_ID}`).reply(200, PART);
    setProduction();
  });

  afterEach(() => {
    mock.restore();
    vi.useRealTimers();
  });

  async function pickPart(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByTestId("job-part-picker-input"));
    await waitFor(() => {
      expect(
        screen.getByTestId(`job-part-picker-option-${PART_ID}`),
      ).toBeInTheDocument();
    });
    await user.click(screen.getByTestId(`job-part-picker-option-${PART_ID}`));
    // Recipe (from the GET /parts/:id fetch) confirms the detail loaded.
    await waitFor(() => {
      expect(screen.getByTestId("job-part-recipe")).toBeInTheDocument();
    });
  }

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

    await pickPart(user);

    await user.clear(screen.getByTestId("job-qty-input"));
    await user.type(screen.getByTestId("job-qty-input"), "4");

    // Advance debounce window.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(350);
    });

    await waitFor(() => {
      expect(screen.getByTestId("cost-total")).toHaveTextContent("$2.10");
    });

    expect(calcCalls.length).toBeGreaterThanOrEqual(1);
    // The calc payload carries the part recipe as a single plate.
    const last = calcCalls[calcCalls.length - 1] as {
      inputs: { plates: Array<{ parts_per_set: number }> };
    };
    expect(last.inputs.plates).toHaveLength(1);
    expect(last.inputs.plates[0]?.parts_per_set).toBe(4);
  });

  it("submits the job with part_id and navigates to its detail page", async () => {
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
      expect(body.part_id).toBe(PART_ID);
      expect(body.quantity_ordered).toBe(2);
      expect(body.product_id).toBeUndefined();
      expect(body.plates).toBeUndefined();
      return [
        201,
        {
          id: "33333333-3333-3333-3333-333333333333",
          job_number: "JOB-2026-0001",
          state: "draft",
          quantity_ordered: 2,
          pieces_produced: 0,
          priority: 0,
          part_id: PART_ID,
          actor_user_id: "u",
          plates: [],
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ];
    });

    renderPage();

    await pickPart(user);

    await user.clear(screen.getByTestId("job-qty-input"));
    await user.type(screen.getByTestId("job-qty-input"), "2");

    await user.click(screen.getByTestId("save-draft-btn"));

    await waitFor(() => {
      expect(screen.getByText("job-detail")).toBeInTheDocument();
    });
  });
});
