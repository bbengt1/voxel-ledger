import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { SyncHealthPanel } from "@/pages/admin/QuickBooksSyncHealth";
import { useAuthStore } from "@/store/useAuthStore";

const DRIFT_ID = "33333333-3333-3333-3333-333333333333";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPanel() {
  return render(
    <MemoryRouter>
      <AppProviders>
        <SyncHealthPanel />
      </AppProviders>
    </MemoryRouter>,
  );
}

function recon(overrides: Record<string, unknown> = {}) {
  return {
    date_from: "2026-03-12",
    date_to: "2026-06-10",
    outbox: { pending: 0, synced: 10, failed: 0, dead: 0, total: 10 },
    gaps: [
      {
        kind: "invoice",
        local_id: "11111111-1111-1111-1111-111111111111",
        reference: "INV-2026-0001",
        occurred_at: "2026-06-01T00:00:00Z",
      },
    ],
    gap_count: 1,
    drift: [],
    drift_open: 1,
    mismatch_candidates: 1,
    decommission_ready: false,
    ...overrides,
  };
}

function driftRow() {
  return {
    id: DRIFT_ID,
    entity_type: "Invoice",
    qbo_id: "555",
    change_type: "updated",
    local_kind: "invoice",
    local_id: "22222222-2222-2222-2222-222222222222",
    occurrences: 2,
    status: "open",
    detail: null,
    first_detected_at: "2026-06-09T00:00:00Z",
    last_detected_at: "2026-06-10T00:00:00Z",
    acknowledged_at: null,
  };
}

describe("<SyncHealthPanel />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    setOwner();
    mock.onGet("/api/v1/admin/quickbooks/reconciliation").reply(200, recon());
    mock.onGet("/api/v1/admin/quickbooks/drift").reply(200, { items: [driftRow()] });
  });

  afterEach(() => {
    mock.restore();
  });

  it("shows the not-ready gate, a gap, and a drift row", async () => {
    renderPanel();
    expect(await screen.findByText("✗ Not decommission-ready")).toBeInTheDocument();
    expect(screen.getByText("INV-2026-0001")).toBeInTheDocument();
    expect(screen.getByText("Gaps: 1")).toBeInTheDocument();
    expect(screen.getByText("555")).toBeInTheDocument();
  });

  it("acknowledges a drift row", async () => {
    const user = userEvent.setup();
    let acked = false;
    mock.onPost(`/api/v1/admin/quickbooks/drift/${DRIFT_ID}/acknowledge`).reply(() => {
      acked = true;
      return [200, { ...driftRow(), status: "acknowledged" }];
    });
    renderPanel();
    await screen.findByText("555");
    await user.click(screen.getByRole("button", { name: "Acknowledge" }));
    await waitFor(() => expect(acked).toBe(true));
  });

  it("renders the ready badge when clean", async () => {
    mock.reset();
    mock
      .onGet("/api/v1/admin/quickbooks/reconciliation")
      .reply(200, recon({ gaps: [], gap_count: 0, drift_open: 0, mismatch_candidates: 0, decommission_ready: true }));
    mock.onGet("/api/v1/admin/quickbooks/drift").reply(200, { items: [] });
    renderPanel();
    expect(await screen.findByText("✓ Decommission-ready")).toBeInTheDocument();
  });
});
