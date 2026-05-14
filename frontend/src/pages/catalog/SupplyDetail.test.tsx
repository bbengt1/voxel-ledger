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
    on_hand: "100",
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
});
