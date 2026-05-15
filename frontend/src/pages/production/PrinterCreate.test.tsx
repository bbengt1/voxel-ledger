import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { PrinterCreatePage } from "@/pages/production/PrinterCreate";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/production/printers/new"]}>
      <AppProviders>
        <Routes>
          <Route
            path="/production/printers/new"
            element={<PrinterCreatePage />}
          />
          <Route
            path="/production/printers/:id"
            element={<div>printer-detail</div>}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<PrinterCreatePage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
  });

  it("submits the form and navigates to detail", async () => {
    setOwner();
    let posted: Record<string, unknown> | null = null;
    mock.onPost("/api/v1/printers").reply((config) => {
      posted = JSON.parse(config.data);
      return [
        201,
        {
          id: "22222222-2222-2222-2222-222222222222",
          name: "P",
          slug: "p1",
          printer_type: "prusa_mk4",
          moonraker_url: null,
          moonraker_api_key_set: true,
          power_draw_watts: null,
          notes: null,
          is_archived: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ];
    });
    renderPage();
    await userEvent.type(screen.getByLabelText(/^name$/i), "P");
    await userEvent.type(screen.getByLabelText(/^slug$/i), "p1");
    await userEvent.type(
      screen.getByLabelText(/moonraker api key/i),
      "shh-secret",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /create printer/i }),
    );
    await screen.findByText("printer-detail");
    expect(posted).not.toBeNull();
    expect((posted as unknown as Record<string, unknown>)["slug"]).toBe("p1");
    expect(
      (posted as unknown as Record<string, unknown>)["moonraker_api_key"],
    ).toBe("shh-secret");
  });

  it("shows error on 400", async () => {
    setOwner();
    mock.onPost("/api/v1/printers").reply(400, { detail: "slug taken" });
    renderPage();
    await userEvent.type(screen.getByLabelText(/^name$/i), "P");
    await userEvent.type(screen.getByLabelText(/^slug$/i), "p1");
    await userEvent.click(
      screen.getByRole("button", { name: /create printer/i }),
    );
    await waitFor(() => {
      expect(screen.getByTestId("create-error")).toHaveTextContent(
        /slug taken/i,
      );
    });
  });
});
