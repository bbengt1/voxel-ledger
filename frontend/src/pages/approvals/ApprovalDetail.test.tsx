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
    expect(screen.getByTestId("cancel-btn")).toBeDisabled();
  });

  it("disables Approve / Reject for the requester (self-approval guard)", async () => {
    setSession("owner", "u-other");
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
    expect(screen.getByTestId("cancel-btn")).not.toBeDisabled();
  });

  it("hides action buttons once the request is decided", async () => {
    setSession("owner", "u-admin");
    mock.onGet(`/api/v1/approvals/${ID}`).reply(
      200,
      row({
        state: "approved",
        decided_by_user_id: "u-admin",
        decided_at: "2026-05-14T01:00:00Z",
      }),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText(/state:/i)).toBeInTheDocument());
    expect(screen.queryByTestId("approve-btn")).not.toBeInTheDocument();
  });

  it("renders the journal-entry payload with a lines table for the large JE type", async () => {
    setSession("owner", "u-admin");
    const acc1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
    const acc2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
    mock.onGet(`/api/v1/approvals/${ID}`).reply(
      200,
      row({
        payload: {
          description: "demo entry",
          posted_at: "2026-05-14T00:00:00Z",
          lines: [
            { account_id: acc1, debit: "1500", credit: "0", memo: "rent" },
            { account_id: acc2, debit: "0", credit: "1500", memo: null },
          ],
        },
      }),
    );
    mock.onGet(`/api/v1/accounts/${acc1}`).reply(200, {
      id: acc1,
      code: "6000",
      name: "Rent expense",
      type: "expense",
      description: null,
      parent_account_id: null,
      is_archived: false,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    mock.onGet(`/api/v1/accounts/${acc2}`).reply(200, {
      id: acc2,
      code: "1000",
      name: "Cash",
      type: "asset",
      description: null,
      parent_account_id: null,
      is_archived: false,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    renderPage();
    expect(
      await screen.findByTestId("payload-journal-entry"),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/Rent expense/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/Cash/)).toBeInTheDocument();
    expect(screen.queryByTestId("payload")).not.toBeInTheDocument();
  });

  it("falls back to <pre> JSON for unknown request types", async () => {
    setSession("owner", "u-admin");
    mock.onGet(`/api/v1/approvals/${ID}`).reply(
      200,
      row({
        request_type: "sales.refund_above_threshold",
        payload: { foo: "bar" },
      }),
    );
    renderPage();
    const pre = await screen.findByTestId("payload");
    expect(pre.tagName).toBe("PRE");
    expect(pre.textContent).toContain("foo");
  });

  it("shows Post entry now only when approved, not consumed, and admin", async () => {
    setSession("bookkeeper", "u-admin");
    mock.onGet(`/api/v1/approvals/${ID}`).reply(
      200,
      row({
        state: "approved",
        decided_by_user_id: "u-admin",
        decided_at: "2026-05-14T01:00:00Z",
        payload: { description: "demo", lines: [] },
      }),
    );
    renderPage();
    expect(await screen.findByTestId("post-entry-now")).toBeInTheDocument();
  });

  it("hides Post entry now once consumed", async () => {
    setSession("owner", "u-admin");
    mock.onGet(`/api/v1/approvals/${ID}`).reply(
      200,
      row({
        state: "approved",
        decided_by_user_id: "u-admin",
        decided_at: "2026-05-14T01:00:00Z",
        consumed_at: "2026-05-14T02:00:00Z",
        payload: { description: "demo", lines: [] },
      }),
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/Consumed at:/i)).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("post-entry-now")).not.toBeInTheDocument();
  });
});
