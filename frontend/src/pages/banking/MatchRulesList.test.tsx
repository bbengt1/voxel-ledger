import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { MatchRulesListPage } from "@/pages/banking/MatchRulesList";
import { useAuthStore } from "@/store/useAuthStore";

const RULE_ID = "11111111-1111-1111-1111-111111111111";

describe("<MatchRulesListPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().setSession({
      accessToken: "a",
      refreshToken: "r",
      user: { id: "u", email: "o@example.com", role: "owner" },
    });
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/bank-match-rules").reply(200, {
      items: [
        {
          id: RULE_ID,
          account_id: null,
          priority: 50,
          match_kind: "regex",
          match_field: "description",
          match_value: "^STARBUCKS",
          min_amount: null,
          max_amount: null,
          action_kind: "ignore",
          debit_account_id: null,
          credit_account_id: null,
          description_template: null,
          notes: null,
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          created_by_user_id: "u",
        },
      ],
    });
  });

  afterEach(() => {
    mock.restore();
  });

  it("smoke renders the row", async () => {
    render(
      <MemoryRouter>
        <AppProviders>
          <MatchRulesListPage />
        </AppProviders>
      </MemoryRouter>,
    );
    await waitFor(() =>
      // DataTable renders a desktop table + mobile card, so the row testid
      // (on the primary cell) appears twice in jsdom.
      expect(
        screen.getAllByTestId(`rule-row-${RULE_ID}`).length,
      ).toBeGreaterThanOrEqual(1),
    );
    expect(screen.getByTestId("run-now-btn")).toBeInTheDocument();
  });
});
