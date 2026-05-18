import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { ExpenseClaimDetailPage } from "@/pages/ap/ExpenseClaimDetail";
import { useAuthStore } from "@/store/useAuthStore";

const CLAIM_ID = "11111111-1111-1111-1111-111111111111";
const SUBMITTER_ID = "22222222-2222-2222-2222-222222222222";

function setUser(role: "owner" | "viewer", id: string) {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id, email: "o@example.com", role },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/expense-claims/${CLAIM_ID}`]}>
      <AppProviders>
        <Routes>
          <Route
            path="/expense-claims/:id"
            element={<ExpenseClaimDetailPage />}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

function claim(submitted: boolean) {
  return {
    id: CLAIM_ID,
    claim_number: "EC-2026-0001",
    submitter_user_id: SUBMITTER_ID,
    state: submitted ? "submitted" : "draft",
    currency: "USD",
    total_amount: "25.00",
    notes: null,
    submitted_at: submitted ? "2026-05-01T00:00:00Z" : null,
    approved_at: null,
    approver_user_id: null,
    rejection_reason: null,
    posting_journal_entry_id: null,
    reimbursement_payment_id: null,
    approval_request_id: null,
    lines: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

describe("<ExpenseClaimDetailPage /> approval guard", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet(`/api/v1/expense-claims/${CLAIM_ID}`).reply(200, claim(true));
  });

  afterEach(() => {
    mock.restore();
  });

  it("hides Approve when the actor is the submitter", async () => {
    setUser("owner", SUBMITTER_ID);
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("claim-state")).toHaveTextContent("submitted"),
    );
    expect(screen.queryByTestId("action-approve")).not.toBeInTheDocument();
    // Reject still shown for admin.
    expect(screen.getByTestId("action-reject")).toBeInTheDocument();
  });

  it("shows Approve when actor differs from submitter", async () => {
    setUser("owner", "different-user-id");
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("claim-state")).toHaveTextContent("submitted"),
    );
    expect(screen.getByTestId("action-approve")).toBeInTheDocument();
  });
});
