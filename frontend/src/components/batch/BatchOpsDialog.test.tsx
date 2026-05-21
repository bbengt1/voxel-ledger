import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { BatchOpsDialog } from "@/components/batch/BatchOpsDialog";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

describe("<BatchOpsDialog />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    mock = new MockAdapter(apiClient);
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("previews then commits and reports the result", async () => {
    mock.onPost("/api/v1/batch/preview").reply(200, {
      entity: "customer",
      action: "archive",
      matched_count: 3,
      sample: [],
      blockers: [{ id: "blk-1", reason: "open invoices" }],
    });
    mock.onPost("/api/v1/batch/commit").reply(200, {
      entity: "customer",
      action: "archive",
      applied: 2,
      skipped: 1,
      audit_id: "aud-1",
      blockers: [{ id: "blk-1", reason: "open invoices" }],
    });

    render(
      <AppProviders>
        <BatchOpsDialog
          open
          onOpenChange={() => {}}
          entity="customer"
          action="archive"
          ids={["a", "b", "c"]}
          title="Archive 3 customers"
        />
      </AppProviders>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("batch-ops-blockers")).toBeInTheDocument(),
    );
    expect(screen.getByText(/open invoices/)).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByTestId("batch-ops-confirm"));
    await waitFor(() =>
      expect(screen.getByTestId("batch-ops-result")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("batch-ops-result")).toHaveTextContent("2");
    expect(screen.getByTestId("batch-ops-result")).toHaveTextContent("1");
  });
});
