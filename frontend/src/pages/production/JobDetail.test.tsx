import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { JobDetailPage } from "@/pages/production/JobDetail";
import { useAuthStore } from "@/store/useAuthStore";

function setProd() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "p@example.com", role: "production" },
  });
}

const JID = "11111111-1111-1111-1111-111111111111";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/production/jobs/${JID}`]}>
      <AppProviders>
        <Routes>
          <Route path="/production/jobs/:id" element={<JobDetailPage />} />
          <Route path="/production/jobs" element={<div>jobs-list</div>} />
          <Route path="/production/jobs/new" element={<div>composer</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<JobDetailPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
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
    setProd();
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders job + plates and fires submit transition", async () => {
    const user = userEvent.setup();
    let submitCalled = false;
    mock.onGet(`/api/v1/jobs/${JID}`).reply(200, {
      id: JID,
      job_number: "JOB-2026-0001",
      state: "draft",
      quantity_ordered: 2,
      pieces_produced: 0,
      priority: 0,
      product_id: "pid",
      actor_user_id: "u",
      plates: [
        {
          id: "pl1",
          job_id: JID,
          name: "Plate A",
          plate_number: 1,
          parts_per_set: 4,
          print_minutes: 60,
          print_hours_setup_minutes: 0,
          print_grams_by_material: {},
          assigned_printer_ids: [],
          runs_completed: 0,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
      notes: null,
      due_at: null,
      customer_id: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    mock.onPost(`/api/v1/jobs/${JID}/submit`).reply(() => {
      submitCalled = true;
      return [200, {}];
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Plate A")).toBeInTheDocument();
    });
    expect(screen.getByTestId("job-state")).toHaveTextContent("draft");

    await user.click(screen.getByTestId("transition-submit"));
    await waitFor(() => expect(submitCalled).toBe(true));
  });

  it("disables Start until a printer is assigned to a plate", async () => {
    mock.onGet(`/api/v1/jobs/${JID}`).reply(200, {
      id: JID,
      job_number: "JOB-2026-0002",
      state: "queued",
      quantity_ordered: 1,
      pieces_produced: 0,
      priority: 0,
      part_id: "part1",
      actor_user_id: "u",
      plates: [
        {
          id: "pl1",
          job_id: JID,
          name: "Plate A",
          plate_number: 1,
          parts_per_set: 1,
          print_minutes: 60,
          print_hours_setup_minutes: 0,
          print_grams_by_material: {},
          assigned_printer_ids: [],
          runs_completed: 0,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
      notes: null,
      due_at: null,
      customer_id: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    mock.onGet("/api/v1/printers").reply(200, {
      items: [{ id: "prn1", name: "Voron", status: "active" }],
    });

    renderPage();

    await waitFor(() => expect(screen.getByTestId("job-state")).toHaveTextContent("queued"));
    // Start is blocked + hint shown while no printer is assigned.
    expect(screen.getByTestId("transition-start")).toBeDisabled();
    expect(screen.getByTestId("start-needs-printer")).toBeInTheDocument();
    // The plate exposes an assign-printer picker so the operator can fix it.
    expect(screen.getByTestId("assign-printer-pl1")).toBeInTheDocument();
  });
});
