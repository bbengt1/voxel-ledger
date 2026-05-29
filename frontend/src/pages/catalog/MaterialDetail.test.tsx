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
    weighted_avg_cost_per_gram: string;
    on_hand_value: string;
    spool_weight_grams: string;
  }> = {},
) {
  return {
    id: MID,
    name: "PLA",
    brand: "Polymaker",
    material_type: "PLA",
    color: "red",
    density_g_per_cm3: "1.24",
    spool_weight_grams: "1000.00",
    current_cost_per_gram: "0.00",
    weighted_avg_cost_per_gram: "0.00",
    on_hand_value: "0.00",
    total_on_hand: "0.00",
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
    // OnHandSection fetches locations for the per-location table label
    // lookup; stub it so tests don't see unrelated 404s.
    mock.onGet("/api/v1/inventory/locations").reply(200, {
      items: [],
      next_cursor: null,
    });
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
          current_cost_per_gram: "20.00",
          weighted_avg_cost_per_gram: "20.00",
          on_hand_value: "20000.00",
          total_on_hand: "1000.00",
        }),
      })
      .onGet(`/api/v1/materials/${MID}`)
      .reply(200, {
        ...aMaterial({
          current_cost_per_gram: "20.00",
          weighted_avg_cost_per_gram: "20.00",
          on_hand_value: "20000.00",
          total_on_hand: "1000.00",
        }),
      });

    renderPage();
    await screen.findByText("Active", { exact: false });
    const user = userEvent.setup();
    await user.click(screen.getByTestId("open-receipt-modal"));
    await user.type(screen.getByTestId("receipt-spools"), "1");
    await user.type(screen.getByTestId("receipt-price-per-spool"), "20000.00");
    await user.click(screen.getByTestId("receipt-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("cost-per-gram")).toHaveTextContent("20.00");
      expect(screen.getByTestId("on-hand-total")).toHaveTextContent("1000.00");
    });
  });

  it("renders the OnHand section with per-location breakdown", async () => {
    mock.reset();
    mock.onGet("/api/v1/inventory/locations").reply(200, {
      items: [
        {
          id: "loc-1",
          name: "Workshop",
          code: "WSB",
          kind: "workshop",
          description: null,
          is_archived: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
      next_cursor: null,
    });
    mock.onGet(`/api/v1/materials/${MID}`).reply(
      200,
      aMaterial({
        total_on_hand: "500.00",
      }),
    );
    // axios-mock-adapter doesn't preserve the second override above for
    // nested objects, so re-assert per_location explicitly:
    mock.onGet(`/api/v1/materials/${MID}`).reply(200, {
      ...aMaterial({ total_on_hand: "500.00" }),
      per_location_on_hand: { "loc-1": "500.00" },
    });

    renderPage();
    const total = await screen.findByTestId("on-hand-total");
    expect(total).toHaveTextContent("500.00");
    await waitFor(() => {
      expect(screen.getByTestId("onhand-per-location")).toHaveTextContent(
        "Workshop",
      );
    });
  });
});
