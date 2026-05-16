import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { ShipmentDetailPage } from "@/pages/sales/ShipmentDetail";
import { ShipmentNewPage } from "@/pages/sales/ShipmentNew";
import { useAuthStore } from "@/store/useAuthStore";

const SALE_ID = "11111111-1111-1111-1111-111111111111";
const SHIPMENT_ID = "22222222-2222-2222-2222-222222222222";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderApp() {
  return render(
    <MemoryRouter initialEntries={[`/sales/${SALE_ID}/shipments/new`]}>
      <AppProviders>
        <Routes>
          <Route
            path="/sales/:id/shipments/new"
            element={<ShipmentNewPage />}
          />
          <Route
            path="/sales/shipments/:id"
            element={<ShipmentDetailPage />}
          />
          <Route path="/sales/:id" element={<div>sale-detail</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

function shipment(state = "pending") {
  return {
    id: SHIPMENT_ID,
    sale_id: SALE_ID,
    state,
    carrier: "shippo",
    cost_amount: "8.50",
    service_level: "usps_priority",
    weight_grams: 200,
    tracking_number: null,
    tracking_url: null,
    label_pdf_storage_key: null,
    dimensions_cm: { length: 10, width: 5, height: 3 },
    ship_from: { name: "Shop", city: "Anywhere", country: "US" },
    ship_to: {
      name: "Jane",
      street1: "1 Main St",
      city: "Springfield",
      state: "IL",
      postal_code: "62701",
      country: "US",
    },
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
  };
}

describe("<ShipmentNewPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet(`/api/v1/sales/${SALE_ID}/shipments`).reply(200, { items: [] });
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("creates a shipment then exposes the purchase-label flow", async () => {
    const user = userEvent.setup();

    let lastBody: Record<string, unknown> | null = null;
    mock.onPost(`/api/v1/sales/${SALE_ID}/shipments`).reply((config) => {
      lastBody = JSON.parse(config.data as string);
      return [201, shipment("pending")];
    });
    mock.onGet(`/api/v1/shipments/${SHIPMENT_ID}`).reply(() => {
      return [200, shipment(lastBody === null ? "pending" : "pending")];
    });
    let purchased = false;
    mock
      .onPost(`/api/v1/shipments/${SHIPMENT_ID}/purchase-label`)
      .reply(() => {
        purchased = true;
        return [200, { ...shipment("label_purchased"), tracking_number: "1Z" }];
      });

    renderApp();

    // Fill in required ship-to fields.
    await user.type(screen.getByTestId("ship-name"), "Jane");
    await user.type(screen.getByTestId("ship-street1"), "1 Main St");
    await user.type(screen.getByTestId("ship-city"), "Springfield");
    await user.type(screen.getByTestId("ship-state"), "IL");
    await user.type(screen.getByTestId("ship-postal"), "62701");
    await user.type(screen.getByTestId("ship-weight"), "200");

    await user.click(screen.getByTestId("shipment-create-btn"));

    // Redirected to shipment detail.
    await waitFor(() => {
      expect(screen.getByTestId("shipment-state")).toHaveTextContent("pending");
    });

    // Purchase-label transition is visible.
    expect(
      screen.getByTestId("transition-purchase-label"),
    ).toBeInTheDocument();

    await user.click(screen.getByTestId("transition-purchase-label"));

    await waitFor(() => {
      expect(purchased).toBe(true);
    });

    // Verify the POST body shape.
    expect(lastBody).not.toBeNull();
    const body = lastBody as unknown as {
      ship_to: { name: string };
      weight_grams: number;
    };
    expect(body.ship_to.name).toBe("Jane");
    expect(body.weight_grams).toBe(200);
  });
});
