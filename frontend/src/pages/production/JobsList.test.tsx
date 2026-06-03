import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { JobsListPage } from "@/pages/production/JobsList";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

const JOB_ID = "11111111-1111-1111-1111-111111111111";

function renderPage(initial = "/production/jobs") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <AppProviders>
        <Routes>
          <Route path="/production/jobs" element={<JobsListPage />} />
          <Route path="/production/jobs/:id" element={<div>job-detail</div>} />
          <Route path="/production/jobs/new" element={<div>composer</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<JobsListPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders jobs and filters by state via URL state", async () => {
    const user = userEvent.setup();
    let lastParams: Record<string, string> | undefined;
    mock.onGet("/api/v1/jobs").reply((config) => {
      lastParams = config.params as Record<string, string>;
      return [
        200,
        {
          items: [
            {
              id: JOB_ID,
              job_number: "JOB-2026-0001",
              state: lastParams?.state ?? "draft",
              quantity_ordered: 2,
              pieces_produced: 0,
              priority: 1,
              product_id: "pid",
              actor_user_id: "u",
              plates: [],
              due_at: null,
              notes: null,
              customer_id: null,
              created_at: "2026-01-01T00:00:00Z",
              updated_at: "2026-01-01T00:00:00Z",
            },
          ],
          next_cursor: null,
        },
      ];
    });

    renderPage();
    await waitFor(() => {
      // DataTable renders a desktop table + mobile card, so cell text appears twice.
      expect(screen.getAllByText("JOB-2026-0001").length).toBeGreaterThanOrEqual(1);
    });

    await user.selectOptions(screen.getByTestId("filter-state"), "queued");

    await waitFor(() => {
      expect(lastParams?.["state"]).toBe("queued");
    });
  });

  it("defaults to in-progress, widens via All, and shows the part", async () => {
    const user = userEvent.setup();
    let lastParams: Record<string, string> | undefined;
    mock.onGet("/api/v1/jobs").reply((config) => {
      lastParams = config.params as Record<string, string>;
      return [
        200,
        {
          items: [
            {
              id: JOB_ID,
              job_number: "JOB-2026-0001",
              state: "in_progress",
              quantity_ordered: 2,
              pieces_produced: 0,
              priority: 1,
              part_id: "pid",
              part_sku: "PART-2026-0001",
              part_name: "Bracket",
              actor_user_id: "u",
              plates: [],
              due_at: null,
              notes: null,
              description: null,
              customer_id: null,
              created_at: "2026-01-01T00:00:00Z",
              updated_at: "2026-01-01T00:00:00Z",
            },
          ],
          next_cursor: null,
        },
      ];
    });

    renderPage();

    // Initial load filters to in-progress without an explicit URL param.
    await waitFor(() => expect(lastParams?.["state"]).toBe("in_progress"));
    expect(screen.getAllByText("Bracket").length).toBeGreaterThanOrEqual(1);

    // Choosing "All" drops the state filter (sentinel, not a snap-back).
    await user.selectOptions(screen.getByTestId("filter-state"), "all");
    await waitFor(() => expect(lastParams?.["state"]).toBeUndefined());
  });
});
