import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { SupplyDetailPage } from "@/pages/catalog/SupplyDetail";
import { useAuthStore } from "@/store/useAuthStore";

const SID = "11111111-1111-1111-1111-111111111111";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function aSupply() {
  return {
    id: SID,
    name: "Bubble Wrap",
    unit: "m",
    unit_cost: "0.25",
    vendor: "ULINE",
    total_on_hand: "100",
    per_location_on_hand: {},
    low_stock_threshold: null,
    is_archived: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/catalog/supplies/${SID}`]}>
      <AppProviders>
        <Routes>
          <Route path="/catalog/supplies/:id" element={<SupplyDetailPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<SupplyDetailPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/inventory/locations").reply(200, {
      items: [],
      next_cursor: null,
    });
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders supply details", async () => {
    setOwner();
    mock.onGet(`/api/v1/supplies/${SID}`).reply(200, aSupply());
    renderPage();
    expect(await screen.findByText("Bubble Wrap")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("unit-cost")).toHaveTextContent("0.25/m");
    });
  });

  it("shows archive button for owner on active supply", async () => {
    setOwner();
    mock.onGet(`/api/v1/supplies/${SID}`).reply(200, aSupply());
    renderPage();
    expect(await screen.findByTestId("archive-btn")).toBeInTheDocument();
  });

  it("renders the OnHand section with per-location breakdown", async () => {
    setOwner();
    mock.reset();
    mock.onGet("/api/v1/inventory/locations").reply(200, {
      items: [
        {
          id: "loc-1",
          name: "Storage",
          code: "STG",
          kind: "workshop",
          description: null,
          is_archived: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
      next_cursor: null,
    });
    mock.onGet(`/api/v1/supplies/${SID}`).reply(200, {
      ...aSupply(),
      total_on_hand: "12",
      per_location_on_hand: { "loc-1": "12" },
    });
    renderPage();
    expect(await screen.findByTestId("on-hand-total")).toHaveTextContent("12");
    await waitFor(() => {
      expect(screen.getByTestId("onhand-per-location")).toHaveTextContent(
        "Storage",
      );
    });
  });
});
