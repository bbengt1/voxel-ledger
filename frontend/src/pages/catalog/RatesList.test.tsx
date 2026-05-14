import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { RatesListPage } from "@/pages/catalog/RatesList";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

const A_ID = "11111111-1111-1111-1111-111111111111";
const B_ID = "22222222-2222-2222-2222-222222222222";

function aRate(
  id: string,
  name: string,
  kind: "labor" | "machine" | "overhead",
  is_default: boolean,
) {
  return {
    id,
    name,
    kind,
    value: "25.00",
    applies_to_printer_id: null,
    is_default_for_kind: is_default,
    is_archived: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/catalog/rates"]}>
      <AppProviders>
        <Routes>
          <Route path="/catalog/rates" element={<RatesListPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<RatesListPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
  });

  it("groups rates by kind", async () => {
    setOwner();
    mock.onGet("/api/v1/rates").reply(200, {
      items: [
        aRate(A_ID, "Labor A", "labor", true),
        aRate(B_ID, "Machine A", "machine", false),
      ],
      next_cursor: null,
    });
    renderPage();
    expect(await screen.findByText("Labor A")).toBeInTheDocument();
    expect(screen.getByTestId("rates-section-labor")).toContainElement(
      screen.getByText("Labor A"),
    );
    expect(screen.getByTestId("rates-section-machine")).toContainElement(
      screen.getByText("Machine A"),
    );
  });

  it("set-default flow flips visually after success", async () => {
    setOwner();
    let getCallCount = 0;
    mock.onGet("/api/v1/rates").reply(() => {
      getCallCount += 1;
      const items =
        getCallCount === 1
          ? [
              aRate(A_ID, "Labor A", "labor", true),
              aRate(B_ID, "Labor B", "labor", false),
            ]
          : [
              aRate(A_ID, "Labor A", "labor", false),
              aRate(B_ID, "Labor B", "labor", true),
            ];
      return [200, { items, next_cursor: null }];
    });
    mock
      .onPost(`/api/v1/rates/${B_ID}/set-default`)
      .reply(200, aRate(B_ID, "Labor B", "labor", true));

    renderPage();
    expect(await screen.findByTestId(`default-marker-${A_ID}`)).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByTestId(`set-default-${B_ID}`));

    await waitFor(() => {
      expect(screen.getByTestId(`default-marker-${B_ID}`)).toBeInTheDocument();
    });
    expect(screen.queryByTestId(`default-marker-${A_ID}`)).not.toBeInTheDocument();
  });
});
