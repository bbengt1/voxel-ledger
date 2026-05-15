import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { PrintersListPage } from "@/pages/production/PrintersList";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function setSales() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "s@example.com", role: "sales" },
  });
}

function aPrinter(
  overrides: Partial<{
    id: string;
    name: string;
    slug: string;
    printer_type: string;
    is_archived: boolean;
    moonraker_api_key_set: boolean;
  }> = {},
) {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    name: "Voron #1",
    slug: "voron-1",
    printer_type: "voron_v2_4",
    moonraker_url: null,
    moonraker_api_key_set: false,
    power_draw_watts: null,
    notes: null,
    is_archived: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/production/printers"]}>
      <AppProviders>
        <Routes>
          <Route path="/production/printers" element={<PrintersListPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<PrintersListPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders rows from the API", async () => {
    setOwner();
    mock.onGet("/api/v1/printers").reply(200, {
      items: [aPrinter()],
      next_cursor: null,
    });
    renderPage();
    expect(await screen.findByText("Voron #1")).toBeInTheDocument();
    expect(screen.getByText("voron-1")).toBeInTheDocument();
    expect(screen.getByText("voron_v2_4")).toBeInTheDocument();
  });

  it("shows New printer for owner", async () => {
    setOwner();
    mock
      .onGet("/api/v1/printers")
      .reply(200, { items: [], next_cursor: null });
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByRole("link", { name: /new printer/i }),
      ).toBeInTheDocument();
    });
  });

  it("hides New printer for sales role", async () => {
    setSales();
    mock
      .onGet("/api/v1/printers")
      .reply(200, { items: [], next_cursor: null });
    renderPage();
    await waitFor(() => {
      expect(
        screen.queryByRole("link", { name: /new printer/i }),
      ).not.toBeInTheDocument();
    });
  });

  it("renders empty state", async () => {
    setOwner();
    mock
      .onGet("/api/v1/printers")
      .reply(200, { items: [], next_cursor: null });
    renderPage();
    expect(
      await screen.findByText(/no printers configured yet/i),
    ).toBeInTheDocument();
  });
});
