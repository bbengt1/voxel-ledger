import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { ExpenseClaimComposerPage } from "@/pages/ap/ExpenseClaimComposer";
import { useAuthStore } from "@/store/useAuthStore";

const CATEGORY_ID = "11111111-1111-1111-1111-111111111111";
const CLAIM_ID = "22222222-2222-2222-2222-222222222222";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/expense-claims/new"]}>
      <AppProviders>
        <Routes>
          <Route
            path="/expense-claims/new"
            element={<ExpenseClaimComposerPage />}
          />
          <Route
            path="/expense-claims/:id"
            element={<div>claim-detail</div>}
          />
          <Route path="/expense-claims" element={<div>claims-list</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<ExpenseClaimComposerPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/expense-categories").reply(200, {
      items: [
        {
          id: CATEGORY_ID,
          code: "MEALS",
          name: "Meals",
          default_expense_account_id: "acct",
          parent_id: null,
          is_active: true,
          notes: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("submits a claim with one line", async () => {
    const user = userEvent.setup();
    let postBody: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/expense-claims").reply((config) => {
      postBody = JSON.parse(config.data as string);
      return [
        201,
        {
          id: CLAIM_ID,
          claim_number: "EC-2026-0001",
          submitter_user_id: "u",
          state: "draft",
          currency: "USD",
          notes: null,
          total_amount: "25.00",
          submitted_at: null,
          approved_at: null,
          approver_user_id: null,
          rejection_reason: null,
          posting_journal_entry_id: null,
          reimbursement_payment_id: null,
          approval_request_id: null,
          lines: [],
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ];
    });

    renderPage();

    // Wait for category options to load by clicking the select then setting value.
    const categorySelect = await screen.findByTestId("line-0-category");
    await user.selectOptions(categorySelect, CATEGORY_ID);

    await user.type(screen.getByTestId("line-0-description"), "Lunch");
    await user.clear(screen.getByTestId("line-0-amount"));
    await user.type(screen.getByTestId("line-0-amount"), "25");

    await user.click(screen.getByTestId("claim-save"));

    await waitFor(() => expect(postBody).toBeDefined());
    const submitted = postBody?.["lines"] as Array<{
      description: string;
      amount: string;
      expense_category_id: string;
    }>;
    expect(submitted).toHaveLength(1);
    expect(submitted[0]?.description).toBe("Lunch");
    expect(submitted[0]?.amount).toBe("25");
    expect(submitted[0]?.expense_category_id).toBe(CATEGORY_ID);
  });
});
