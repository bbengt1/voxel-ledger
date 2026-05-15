import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { ApprovalDetailPage } from "@/pages/approvals/ApprovalDetail";
import { useAuthStore } from "@/store/useAuthStore";

const ID = "11111111-1111-1111-1111-111111111111";

function setSession(
  role: "owner" | "bookkeeper" | "sales",
  id: string = "u-other",
) {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id, email: `${role}@x.com`, role },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/approvals/${ID}`]}>
      <AppProviders>
        <Routes>
          <Route path="/approvals/:id" element={<ApprovalDetailPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

function row(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: ID,
    request_type: "accounting.large_journal_entry",
    subject_kind: "journal_entry",
    subject_id: "sub-id",
    requested_by_user_id: "u-other",
    requested_at: "2026-05-14T00:00:00Z",
    state: "pending",
    decided_by_user_id: null,
    decided_at: null,
    decision_note: null,
    payload: { description: "demo", lines: [] },
    threshold_amount: "1000.00",
    consumed_at: null,
    ...overrides,
  };
}

describe("<ApprovalDetailPage />", () => {
  let mock: MockAdapter;
  beforeEach(() => {
    useAuthStore.getState().clearSession();
    mock = new MockAdapter(apiClient);
  });
  afterEach(() => mock.restore());

  it("enables Approve / Reject for an admin who isn't the requester", async () => {
    setSession("bookkeeper", "u-admin");
    mock.onGet(`/api/v1/approvals/${ID}`).reply(200, row());
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("approve-btn")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("approve-btn")).not.toBeDisabled();
    expect(screen.getByTestId("reject-btn")).not.toBeDisabled();
    // Cancel: bookkeeper is not the requester and not owner → disabled.
    expect(screen.getByTestId("cancel-btn")).toBeDisabled();
  });

  it("disables Approve / Reject for the requester (self-approval guard)", async () => {
    setSession("owner", "u-other"); // requester id matches
    mock.onGet(`/api/v1/approvals/${ID}`).reply(200, row());
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("approve-btn")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("approve-btn")).toBeDisabled();
    expect(screen.getByTestId("approve-btn")).toHaveAttribute(
      "title",
      expect.stringMatching(/your own/i) as unknown as string,
    );
    expect(screen.getByTestId("reject-btn")).toBeDisabled();
    // The requester can still cancel their own request.
    expect(screen.getByTestId("cancel-btn")).not.toBeDisabled();
  });

  it("hides action buttons once the request is decided", async () => {
    setSession("owner", "u-admin");
    mock
      .onGet(`/api/v1/approvals/${ID}`)
      .reply(200, row({ state: "approved", decided_by_user_id: "u-admin", decided_at: "2026-05-14T01:00:00Z" }));
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/state:/i)).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("approve-btn")).not.toBeInTheDocument();
  });

  it("renders the payload as <pre>", async () => {
    setSession("owner", "u-admin");
    mock.onGet(`/api/v1/approvals/${ID}`).reply(200, row());
    renderPage();
    const pre = await screen.findByTestId("payload");
    expect(pre.tagName).toBe("PRE");
    expect(pre.textContent).toContain("demo");
  });
});
