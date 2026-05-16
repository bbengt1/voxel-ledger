import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { RefundComposerPage } from "@/pages/sales/RefundComposer";
import { useAuthStore } from "@/store/useAuthStore";

const SALE_ID = "33333333-3333-3333-3333-333333333333";
const REFUND_ID = "44444444-4444-4444-4444-444444444444";
const ITEM_ID = "55555555-5555-5555-5555-555555555555";

function setSession() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u1", email: "c@x.com", role: "sales" },
  });
}

function saleResponse(unitPrice = "100") {
  return {
    id: SALE_ID,
    sale_number: "S-1001",
    channel_id: "ch-1",
    channel_fee_amount: "0",
    customer_name: "Alice",
    customer_email: null,
    discount_amount: "0",
    shipping_amount: "0",
    notes: null,
    occurred_at: "2026-05-01T00:00:00Z",
    recorded_at: "2026-05-01T00:00:00Z",
    created_at: "2026-05-01T00:00:00Z",
    created_by_user_id: "u1",
    external_order_id: null,
    sale_id: SALE_ID,
    items: [
      {
        id: ITEM_ID,
        line_number: 1,
        description: "Widget A",
        extended_amount: unitPrice,
        kind: "product",
        quantity: "1",
        unit_price: unitPrice,
      },
    ],
  };
}

function renderPage(initialPath = `/sales/${SALE_ID}/refund/new`) {
  // Capture navigation by mounting a sink route at each known target.
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AppProviders>
        <Routes>
          <Route
            path="/sales/:id/refund/new"
            element={<RefundComposerPage />}
          />
          <Route
            path="/sales/refunds/:id"
            element={<div data-testid="refund-detail-page" />}
          />
          <Route
            path="/approvals"
            element={<div data-testid="approvals-page" />}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<RefundComposerPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    setSession();
    mock = new MockAdapter(apiClient);
    mock
      .onGet(/\/api\/v1\/settings\/sales\.refund\.approval_threshold/)
      .reply(200, {
        key: "sales.refund.approval_threshold",
        value: "500",
        default: "500",
        schema_type: "Decimal",
      });
  });
  afterEach(() => mock.restore());

  it("over-threshold shows approval routing notice and redirects to approvals", async () => {
    mock.onGet(`/api/v1/sales/${SALE_ID}`).reply(200, saleResponse("800"));
    mock.onPost("/api/v1/refunds").reply(202, {
      refund: {
        id: REFUND_ID,
        refund_number: "R-1",
        sale_id: SALE_ID,
        kind: "partial",
        reason_code: "damaged",
        restock_inventory: true,
        state: "pending_approval",
        total_amount: "800.00",
        created_at: "2026-05-15T00:00:00Z",
        created_by_user_id: "u1",
        items: [],
      },
      approval_request_id: "approval-1",
    });

    renderPage();
    const checkbox = await screen.findByTestId("line-checkbox-1");
    await userEvent.click(checkbox);

    expect(await screen.findByTestId("approval-notice")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("submit-refund"));
    expect(await screen.findByTestId("approvals-page")).toBeInTheDocument();
  });

  it("under-threshold redirects to refund detail", async () => {
    mock.onGet(`/api/v1/sales/${SALE_ID}`).reply(200, saleResponse("100"));
    mock.onPost("/api/v1/refunds").reply(201, {
      refund: {
        id: REFUND_ID,
        refund_number: "R-2",
        sale_id: SALE_ID,
        kind: "partial",
        reason_code: "damaged",
        restock_inventory: true,
        state: "approved",
        total_amount: "100.00",
        created_at: "2026-05-15T00:00:00Z",
        created_by_user_id: "u1",
        items: [],
      },
      approval_request_id: null,
    });

    renderPage();
    const checkbox = await screen.findByTestId("line-checkbox-1");
    await userEvent.click(checkbox);
    // No approval banner under threshold.
    await waitFor(() =>
      expect(screen.queryByTestId("approval-notice")).not.toBeInTheDocument(),
    );

    await userEvent.click(screen.getByTestId("submit-refund"));
    expect(
      await screen.findByTestId("refund-detail-page"),
    ).toBeInTheDocument();
  });
});
