import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { TransactionsListPage } from "@/pages/banking/TransactionsList";
import { useAuthStore } from "@/store/useAuthStore";

const TX_ID = "11111111-1111-1111-1111-111111111111";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

describe("<TransactionsListPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/accounts").reply(200, { items: [] });
    mock.onGet("/api/v1/bank-transactions").reply(200, {
      items: [
        {
          id: TX_ID,
          account_id: "acct",
          amount: "-12.34",
          description: "Coffee",
          memo: null,
          state: "unmatched",
          occurred_on: "2026-05-01",
          imported_at: "2026-05-01T00:00:00Z",
          import_run_id: null,
          fitid: null,
          matched_journal_line_id: null,
          running_balance: null,
          external_hash: "abc",
          created_at: "2026-05-01T00:00:00Z",
          updated_at: "2026-05-01T00:00:00Z",
        },
      ],
      next_cursor: null,
    });
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders rows and inline actions", async () => {
    render(
      <MemoryRouter initialEntries={["/banking/transactions"]}>
        <AppProviders>
          <TransactionsListPage />
        </AppProviders>
      </MemoryRouter>,
    );
    await waitFor(() =>
      // DataTable renders a desktop table + mobile card, so row + action
      // testids appear twice in jsdom.
      expect(
        screen.getAllByTestId(`tx-row-${TX_ID}`).length,
      ).toBeGreaterThanOrEqual(1),
    );
    expect(
      screen.getAllByTestId(`tx-match-${TX_ID}`).length,
    ).toBeGreaterThanOrEqual(1);
    expect(
      screen.getAllByTestId(`tx-post-${TX_ID}`).length,
    ).toBeGreaterThanOrEqual(1);
    expect(
      screen.getAllByTestId(`tx-ignore-${TX_ID}`).length,
    ).toBeGreaterThanOrEqual(1);
  });
});
