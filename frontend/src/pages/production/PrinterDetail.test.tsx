import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { PrinterDetailPage } from "@/pages/production/PrinterDetail";
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
    <MemoryRouter initialEntries={[`/production/printers/${PID}`]}>
      <AppProviders>
        <Routes>
          <Route
            path="/production/printers/:id"
            element={<PrinterDetailPage />}
          />
          <Route
            path="/production/printers"
            element={<div>printers-list</div>}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<PrinterDetailPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders printer + shows camera snapshot when configured", async () => {
    setOwner();
    mock.onGet(`/api/v1/printers/${PID}`).reply(200, {
      id: PID,
      name: "Voron #1",
      slug: "voron-1",
      printer_type: "voron_v2_4",
      moonraker_url: "http://10/x",
      moonraker_api_key_set: true,
      power_draw_watts: 350,
      notes: null,
      is_archived: false,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    mock.onGet(`/api/v1/printers/${PID}/cameras`).reply(200, {
      id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
      printer_id: PID,
      kind: "go2rtc",
      snapshot_url: "http://cam/snap.jpg",
      username: "wyze",
      password_secret_set: true,
      is_active: true,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });

    renderPage();
    expect(await screen.findByText("Voron #1")).toBeInTheDocument();
    const snap = await screen.findByTestId("camera-snapshot");
    expect(snap).toHaveAttribute(
      "src",
      `/api/v1/printers/${PID}/cameras/snapshot.jpg`,
    );
    // The page advertises the camera as configured with a stored password.
    expect(screen.getByText(/password stored/i)).toBeInTheDocument();
  });

  it("handles no camera configured", async () => {
    setOwner();
    mock.onGet(`/api/v1/printers/${PID}`).reply(200, {
      id: PID,
      name: "P",
      slug: "p1",
      printer_type: "prusa_mk4",
      moonraker_url: null,
      moonraker_api_key_set: false,
      power_draw_watts: null,
      notes: null,
      is_archived: false,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    mock
      .onGet(`/api/v1/printers/${PID}/cameras`)
      .reply(404, { detail: "camera not configured" });

    renderPage();
    await screen.findByText("P");
    await waitFor(() => {
      expect(screen.getByText(/no camera configured/i)).toBeInTheDocument();
    });
  });
});
