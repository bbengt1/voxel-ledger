import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { ReconciliationBoardPage } from "@/pages/banking/ReconciliationBoard";
import { useAuthStore } from "@/store/useAuthStore";

const RECON_ID = "11111111-1111-1111-1111-111111111111";
const ITEM_ID = "22222222-2222-2222-2222-222222222222";
const TX_ID = "33333333-3333-3333-3333-333333333333";
const ACCOUNT_ID = "44444444-4444-4444-4444-444444444444";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function setupMocks(mock: MockAdapter, stmt: string, amount: string) {
  mock.onGet(`/api/v1/bank-reconciliations/${RECON_ID}`).reply(200, {
    id: RECON_ID,
    account_id: ACCOUNT_ID,
    period_start: "2026-05-01",
    period_end: "2026-05-31",
    state: "open",
    statement_ending_balance: stmt,
    book_ending_balance: null,
    difference: null,
    notes: null,
    finalized_at: null,
    finalized_by_user_id: null,
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    created_by_user_id: "u",
    items: [
      {
        id: ITEM_ID,
        bank_transaction_id: TX_ID,
        reconciliation_id: RECON_ID,
        is_cleared: false,
        created_at: "2026-05-01T00:00:00Z",
        updated_at: "2026-05-01T00:00:00Z",
      },
    ],
  });
  mock.onGet("/api/v1/bank-transactions").reply(200, {
    items: [
      {
        id: TX_ID,
        account_id: ACCOUNT_ID,
        amount,
        description: "Item",
        memo: null,
        state: "matched",
        occurred_on: "2026-05-10",
        imported_at: "2026-05-10T00:00:00Z",
        import_run_id: null,
        fitid: null,
        matched_journal_line_id: null,
        running_balance: null,
        external_hash: "h",
        created_at: "2026-05-10T00:00:00Z",
        updated_at: "2026-05-10T00:00:00Z",
      },
    ],
    next_cursor: null,
  });
  mock
    .onPost(`/api/v1/bank-reconciliations/${RECON_ID}/items/${ITEM_ID}/clear`)
    .reply(200, {});
  mock
    .onPost(`/api/v1/bank-reconciliations/${RECON_ID}/items/${ITEM_ID}/unclear`)
    .reply(200, {});
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/banking/reconciliation/${RECON_ID}`]}>
      <AppProviders>
        <Routes>
          <Route
            path="/banking/reconciliation/:id"
            element={<ReconciliationBoardPage />}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<ReconciliationBoardPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("updates the displayed difference when an item is toggled cleared", async () => {
    setupMocks(mock, "50.00", "50.00");
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("recon-difference")).toHaveTextContent("50.00"),
    );
    await user.click(screen.getByTestId(`recon-check-${ITEM_ID}`));
    await waitFor(() =>
      expect(screen.getByTestId("recon-difference")).toHaveTextContent("0.00"),
    );
  });

  it("disables Finalize when difference != 0", async () => {
    setupMocks(mock, "50.00", "10.00");
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("recon-finalize")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("recon-finalize")).toBeDisabled();
  });

  it("enables Finalize once cleared items zero out the difference", async () => {
    setupMocks(mock, "50.00", "50.00");
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("recon-finalize")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("recon-finalize")).toBeDisabled();
    await user.click(screen.getByTestId(`recon-check-${ITEM_ID}`));
    await waitFor(() =>
      expect(screen.getByTestId("recon-finalize")).not.toBeDisabled(),
    );
  });
});
