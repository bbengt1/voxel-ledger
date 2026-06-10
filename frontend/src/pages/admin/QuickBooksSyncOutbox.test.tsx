import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { SyncOutboxMonitor } from "@/pages/admin/QuickBooksSyncOutbox";
import { useAuthStore } from "@/store/useAuthStore";

const ROW_ID = "11111111-1111-1111-1111-111111111111";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderMonitor() {
  return render(
    <MemoryRouter>
      <AppProviders>
        <SyncOutboxMonitor />
      </AppProviders>
    </MemoryRouter>,
  );
}

function failedRow() {
  return {
    id: ROW_ID,
    kind: "bill",
    local_id: "22222222-2222-2222-2222-222222222222",
    op: "post",
    status: "failed",
    attempts: 3,
    qbo_entity_type: null,
    qbo_id: null,
    last_error: "account not mapped",
    next_attempt_at: "2026-06-10T00:00:00Z",
    created_at: "2026-06-10T00:00:00Z",
    updated_at: "2026-06-10T00:00:00Z",
  };
}

describe("<SyncOutboxMonitor />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    setOwner();
    mock
      .onGet("/api/v1/admin/quickbooks/outbox/stats")
      .reply(200, { pending: 1, synced: 5, failed: 1, dead: 0, total: 7 });
    mock.onGet("/api/v1/admin/quickbooks/outbox").reply(200, { items: [failedRow()] });
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders stats + rows and retries a failed row", async () => {
    const user = userEvent.setup();
    let retried = false;
    mock.onPost(`/api/v1/admin/quickbooks/outbox/${ROW_ID}/retry`).reply(() => {
      retried = true;
      return [200, { ...failedRow(), status: "pending" }];
    });

    renderMonitor();

    expect(await screen.findByText("account not mapped")).toBeInTheDocument();
    expect(screen.getByText("Failed: 1")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(retried).toBe(true));
  });

  it("bulk-retries all failed rows", async () => {
    const user = userEvent.setup();
    let bulk: { status?: string } | undefined;
    mock.onPost("/api/v1/admin/quickbooks/outbox/retry").reply((config) => {
      bulk = JSON.parse(config.data as string);
      return [200, { requeued: 1 }];
    });
    // auto-confirm the window.confirm guard
    viSpyConfirm();

    renderMonitor();
    await screen.findByText("account not mapped");

    await user.click(screen.getByRole("button", { name: /Retry all failed/ }));
    await waitFor(() => expect(bulk?.status).toBe("failed"));
  });
});

function viSpyConfirm() {
  // jsdom's confirm returns undefined; force-accept.
  window.confirm = () => true;
}
