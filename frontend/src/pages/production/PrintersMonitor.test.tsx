import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { PrintersMonitorPage } from "@/pages/production/PrintersMonitor";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

const PID = "11111111-1111-1111-1111-111111111111";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/production/printers"]}>
      <AppProviders>
        <Routes>
          <Route path="/production/printers" element={<PrintersMonitorPage />} />
          <Route path="/production/printers/:id" element={<div>detail</div>} />
          <Route path="/production/printers/new" element={<div>create</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<PrintersMonitorPage />", () => {
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

  it("renders a printer card with state badge + snapshot", async () => {
    mock.onGet("/api/v1/printers").reply(200, {
      items: [
        {
          id: PID,
          name: "Voron #1",
          slug: "voron-1",
          printer_type: "voron_v2_4",
          moonraker_url: null,
          moonraker_api_key_set: false,
          power_draw_watts: 350,
          notes: null,
          is_archived: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
      next_cursor: null,
    });
    mock.onGet(`/api/v1/printers/${PID}/state`).reply(200, {
      printer_id: PID,
      state: "printing",
      progress_pct: 42,
      current_file: "widget.gcode",
      elapsed_seconds: 600,
      remaining_seconds_estimate: 900,
      last_seen_at: "2026-05-15T13:00:00Z",
      temperatures: { extruder: 215.5, bed: 60.0 },
    });
    mock.onGet(`/api/v1/printers/${PID}/cameras`).reply(200, {
      id: "ccc",
      printer_id: PID,
      kind: "go2rtc",
      snapshot_url: "http://cam/snap.jpg",
      password_secret_set: false,
      is_active: true,
      username: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });

    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Voron #1")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId(`printer-card-state-${PID}`)).toHaveTextContent(
        "printing",
      );
    });
    expect(screen.getByTestId(`printer-snapshot-${PID}`)).toHaveAttribute(
      "src",
      expect.stringContaining(`/api/v1/printers/${PID}/cameras/snapshot.jpg`),
    );
    expect(screen.getByTestId(`printer-progress-${PID}`)).toHaveTextContent(
      "42%",
    );
  });

  it("shows a warmup banner with Retry-After when state is 503 and recovers on retry", async () => {
    const user = userEvent.setup();
    mock.onGet("/api/v1/printers").reply(200, {
      items: [
        {
          id: PID,
          name: "Voron #2",
          slug: "voron-2",
          printer_type: "voron_v2_4",
          moonraker_url: null,
          moonraker_api_key_set: false,
          power_draw_watts: null,
          notes: null,
          is_archived: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
      next_cursor: null,
    });
    mock.onGet(`/api/v1/printers/${PID}/cameras`).reply(404);

    let callCount = 0;
    mock.onGet(`/api/v1/printers/${PID}/state`).reply(() => {
      callCount += 1;
      if (callCount === 1) {
        return [503, { detail: "warming up" }, { "retry-after": "7" }];
      }
      return [
        200,
        {
          printer_id: PID,
          state: "idle",
          progress_pct: null,
          current_file: null,
          elapsed_seconds: null,
          remaining_seconds_estimate: null,
          last_seen_at: null,
          temperatures: { extruder: null, bed: null },
        },
      ];
    });

    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId(`printer-warmup-${PID}`)).toHaveTextContent(
        "retry in 7s",
      );
    });

    await act(async () => {
      await user.click(screen.getByTestId(`printer-warmup-retry-${PID}`));
    });

    await waitFor(() => {
      expect(screen.getByTestId(`printer-card-state-${PID}`)).toHaveTextContent(
        "idle",
      );
    });
  });
});
