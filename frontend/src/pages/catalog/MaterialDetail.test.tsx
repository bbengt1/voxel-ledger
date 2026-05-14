import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { MaterialDetailPage } from "@/pages/catalog/MaterialDetail";
import { useAuthStore } from "@/store/useAuthStore";

const MID = "11111111-1111-1111-1111-111111111111";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function aMaterial(
  overrides: Partial<{
    current_cost_per_gram: string;
    total_on_hand: string;
  }> = {},
) {
  return {
    id: MID,
    name: "PLA",
    brand: "Polymaker",
    material_type: "PLA",
    color: "red",
    density_g_per_cm3: "1.24",
    current_cost_per_gram: "0.000000",
    total_on_hand: "0.000000",
    per_location_on_hand: {},
    low_stock_threshold_grams: null,
    is_archived: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    recent_receipts: [],
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/catalog/materials/${MID}`]}>
      <AppProviders>
        <Routes>
          <Route
            path="/catalog/materials/:id"
            element={<MaterialDetailPage />}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<MaterialDetailPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    setOwner();
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
  });

  it("loads, edits, and saves the profile", async () => {
    mock.onGet(`/api/v1/materials/${MID}`).reply(200, aMaterial());
    let observedBody: Record<string, unknown> | undefined;
    mock.onPatch(`/api/v1/materials/${MID}`).reply((config) => {
      observedBody = JSON.parse(config.data ?? "{}");
      return [200, { ...aMaterial(), name: "PLA Pro" }];
    });

    renderPage();
    await screen.findByText("Active", { exact: false });
    const user = userEvent.setup();
    // The name input is the first labelled "Name" field on the form.
    const nameInput = screen.getByLabelText(/^name$/i);
    await user.clear(nameInput);
    await user.type(nameInput, "PLA Pro");
    await user.click(screen.getByTestId("save-btn"));
    await screen.findByTestId("save-msg");
    expect(observedBody).toMatchObject({ name: "PLA Pro" });
  });

  it("records a receipt and refreshes cost display", async () => {
    mock
      .onGet(`/api/v1/materials/${MID}`)
      .replyOnce(200, aMaterial())
      .onPost(`/api/v1/materials/${MID}/receipts`)
      .reply(201, {
        ...aMaterial({
          current_cost_per_gram: "20.000000",
          total_on_hand: "1000.000000",
        }),
      })
      .onGet(`/api/v1/materials/${MID}`)
      .reply(200, {
        ...aMaterial({
          current_cost_per_gram: "20.000000",
          total_on_hand: "1000.000000",
        }),
      });

    renderPage();
    await screen.findByText("Active", { exact: false });
    const user = userEvent.setup();
    await user.click(screen.getByTestId("open-receipt-modal"));
    await user.type(screen.getByTestId("receipt-grams"), "1000");
    await user.type(screen.getByTestId("receipt-total-cost"), "20000.00");
    await user.click(screen.getByTestId("receipt-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("cost-per-gram")).toHaveTextContent(
        "20.000000",
      );
      expect(screen.getByTestId("on-hand")).toHaveTextContent(
        "1000.000000",
      );
    });
  });
});
