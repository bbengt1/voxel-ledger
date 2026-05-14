import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { RateDetailPage } from "@/pages/catalog/RateDetail";
import { useAuthStore } from "@/store/useAuthStore";

const RID = "11111111-1111-1111-1111-111111111111";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function aRate(
  overrides: Partial<{ is_default_for_kind: boolean; is_archived: boolean }> = {},
) {
  return {
    id: RID,
    name: "Labor A",
    kind: "labor" as const,
    value: "25.00",
    applies_to_printer_id: null,
    is_default_for_kind: false,
    is_archived: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/catalog/rates/${RID}`]}>
      <AppProviders>
        <Routes>
          <Route path="/catalog/rates/:id" element={<RateDetailPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<RateDetailPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders rate details", async () => {
    setOwner();
    mock.onGet(`/api/v1/rates/${RID}`).reply(200, aRate());
    renderPage();
    expect(await screen.findByText("Labor A")).toBeInTheDocument();
  });

  it("set-default button posts and refreshes", async () => {
    setOwner();
    mock.onGet(`/api/v1/rates/${RID}`).reply(200, aRate());
    mock
      .onPost(`/api/v1/rates/${RID}/set-default`)
      .reply(200, aRate({ is_default_for_kind: true }));

    renderPage();
    expect(await screen.findByTestId("set-default-btn")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByTestId("set-default-btn"));

    await waitFor(() => {
      expect(screen.getByText(/default ·/i)).toBeInTheDocument();
    });
  });
});
