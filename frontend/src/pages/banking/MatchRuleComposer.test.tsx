import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { MatchRuleComposerPage } from "@/pages/banking/MatchRuleComposer";
import { useAuthStore } from "@/store/useAuthStore";

const DEBIT_ID = "11111111-1111-1111-1111-111111111111";
const CREDIT_ID = "22222222-2222-2222-2222-222222222222";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/banking/match-rules/new"]}>
      <AppProviders>
        <Routes>
          <Route
            path="/banking/match-rules/new"
            element={<MatchRuleComposerPage />}
          />
          <Route path="/banking/match-rules" element={<div>list</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<MatchRuleComposerPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/accounts").reply(200, {
      items: [
        {
          id: DEBIT_ID,
          code: "5000",
          name: "Coffee",
          type: "expense",
          is_archived: false,
          parent_account_id: null,
          description: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
        {
          id: CREDIT_ID,
          code: "1010",
          name: "Checking",
          type: "asset",
          is_archived: false,
          parent_account_id: null,
          description: null,
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

  it("flags an invalid regex client-side", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByTestId("match-kind-regex"));
    await user.type(screen.getByTestId("rule-match-value"), "(unclosed");
    await waitFor(() =>
      expect(screen.getByTestId("rule-regex-error")).toBeInTheDocument(),
    );
  });

  it("requires both contra accounts when action is post_to_account", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByTestId("rule-match-value"), "STARBUCKS");
    await user.click(screen.getByTestId("action-kind-post_to_account"));
    await user.click(screen.getByTestId("save-rule"));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        /both debit and credit/i,
      ),
    );
  });

  it("submits valid post_to_account body", async () => {
    const user = userEvent.setup();
    let body: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/bank-match-rules").reply((config) => {
      body = JSON.parse(config.data as string);
      return [201, { id: "x" }];
    });

    renderPage();
    await user.type(screen.getByTestId("rule-match-value"), "STARBUCKS");
    await user.click(screen.getByTestId("action-kind-post_to_account"));
    await waitFor(() =>
      expect(
        screen
          .getByTestId("rule-debit-account")
          .querySelector(`option[value="${DEBIT_ID}"]`),
      ).not.toBeNull(),
    );
    await user.selectOptions(screen.getByTestId("rule-debit-account"), DEBIT_ID);
    await user.selectOptions(
      screen.getByTestId("rule-credit-account"),
      CREDIT_ID,
    );
    await user.click(screen.getByTestId("save-rule"));

    await waitFor(() => expect(body).toBeDefined());
    expect(body?.["match_value"]).toBe("STARBUCKS");
    expect(body?.["action_kind"]).toBe("post_to_account");
    expect(body?.["debit_account_id"]).toBe(DEBIT_ID);
    expect(body?.["credit_account_id"]).toBe(CREDIT_ID);
  });
});
