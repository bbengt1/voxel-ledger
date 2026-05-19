import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { SettlementBoardPage } from "@/pages/settlements/SettlementBoard";
import { useAuthStore } from "@/store/useAuthStore";

const SETTLEMENT_ID = "ssssssss-ssss-ssss-ssss-ssssssssssss";
const LINE_ID = "11111111-1111-1111-1111-111111111111";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function settlementBody(state: "imported" | "matched" | "posted") {
  return {
    settlement: {
      id: SETTLEMENT_ID,
      settlement_number: "SETT-0001",
      channel_id: "chan-1",
      period_start: "2026-04-01",
      period_end: "2026-04-30",
      gross_amount: "20.00",
      fee_amount: "1.30",
      refund_amount: "0.00",
      adjustment_amount: "0.00",
      payout_amount: "18.70",
      payout_account_id: "acc-bank",
      filename: "etsy.csv",
      imported_at: "2026-05-01T00:00:00Z",
      imported_by_user_id: "u",
      state,
      posting_journal_entry_id: null,
      notes: null,
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-01T00:00:00Z",
    },
    lines: [
      {
        id: LINE_ID,
        settlement_id: SETTLEMENT_ID,
        line_number: 1,
        line_kind: "sale",
        occurred_on: "2026-04-15",
        description: "",
        external_order_id: "ETSY-1",
        external_txn_id: null,
        amount: "20.00",
        state: "unmatched",
        matched_sale_id: null,
        matched_refund_id: null,
        created_at: "2026-05-01T00:00:00Z",
        updated_at: "2026-05-01T00:00:00Z",
      },
    ],
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/settlements/${SETTLEMENT_ID}`]}>
      <AppProviders>
        <Routes>
          <Route path="/settlements/:id" element={<SettlementBoardPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<SettlementBoardPage />", () => {
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

  it("disables the Post button while sale/refund lines are unmatched", async () => {
    mock
      .onGet(`/api/v1/settlements/${SETTLEMENT_ID}`)
      .reply(200, settlementBody("imported"));
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("post-settlement")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("post-settlement")).toBeDisabled();
  });

  it("Run auto-match wires up the action", async () => {
    let called = false;
    mock
      .onGet(`/api/v1/settlements/${SETTLEMENT_ID}`)
      .reply(200, settlementBody("imported"));
    mock
      .onPost(`/api/v1/settlements/${SETTLEMENT_ID}/match-now`)
      .reply(() => {
        called = true;
        return [200, { matched: 1, unmatched: 0 }];
      });

    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("auto-match")).toBeInTheDocument(),
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId("auto-match"));
    await waitFor(() => expect(called).toBe(true));
  });
});
