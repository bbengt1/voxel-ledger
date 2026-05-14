import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { OnHandSection } from "@/components/inventory/OnHandSection";
import { useAuthStore } from "@/store/useAuthStore";

const LOCS = [
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
];

function setRole(role: "owner" | "viewer") {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "e@e", role },
  });
}

describe("<OnHandSection />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    mock = new MockAdapter(apiClient);
    mock
      .onGet("/api/v1/inventory/locations")
      .reply(200, { items: LOCS, next_cursor: null });
  });
  afterEach(() => {
    mock.restore();
  });

  it("renders the total + per-location breakdown sorted desc", async () => {
    setRole("owner");
    render(
      <OnHandSection
        entityKind="material"
        entityId="m-1"
        entityName="PLA"
        totalOnHand="500"
        perLocationOnHand={{ "loc-1": "500" }}
        unit="g"
        lowStockThreshold={null}
      />,
    );
    expect(screen.getByTestId("on-hand-total")).toHaveTextContent("500");
    await waitFor(() =>
      expect(screen.getByTestId("onhand-per-location")).toHaveTextContent(
        "Workshop",
      ),
    );
  });

  it("hides write affordances for viewer role", () => {
    setRole("viewer");
    render(
      <OnHandSection
        entityKind="material"
        entityId="m-1"
        entityName="PLA"
        totalOnHand="0"
        perLocationOnHand={null}
        unit="g"
        lowStockThreshold={null}
      />,
    );
    expect(screen.queryByTestId("onhand-record-receipt")).not.toBeInTheDocument();
    expect(screen.queryByTestId("onhand-transfer")).not.toBeInTheDocument();
    expect(screen.queryByTestId("threshold-edit")).not.toBeInTheDocument();
  });

  it("hides the Transfer button for supplies (owner)", () => {
    setRole("owner");
    render(
      <OnHandSection
        entityKind="supply"
        entityId="s-1"
        entityName="Tape"
        totalOnHand="0"
        perLocationOnHand={null}
        unit="ea"
        lowStockThreshold={null}
      />,
    );
    expect(screen.queryByTestId("onhand-transfer")).not.toBeInTheDocument();
    expect(screen.getByTestId("onhand-record-receipt")).toBeInTheDocument();
  });
});
