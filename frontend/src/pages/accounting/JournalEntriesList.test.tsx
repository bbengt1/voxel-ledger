import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { JournalEntriesListPage } from "@/pages/accounting/JournalEntriesList";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@x.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/accounting/entries"]}>
      <AppProviders>
        <JournalEntriesListPage />
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<JournalEntriesListPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/accounting/periods").reply(200, {
      items: [
        {
          id: "p1",
          name: "2026-Q1",
          start_date: "2026-01-01",
          end_date: "2026-03-31",
          state: "open",
          closed_at: null,
          closed_by_user_id: null,
          locked_at: null,
          locked_by_user_id: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
      next_cursor: null,
    });
  });

  afterEach(() => mock.restore());

  it("renders entries from the API", async () => {
    setOwner();
    mock.onGet("/api/v1/accounting/entries").reply(200, {
      items: [
        {
          id: "e1",
          entry_number: "JE-00007",
          description: "October utility",
          posted_at: "2026-10-01T00:00:00Z",
          period_id: "p1",
          actor_user_id: "u",
          is_reversed: false,
          reversal_of_entry_id: null,
          created_at: "2026-10-01T00:00:00Z",
          lines: [
            {
              id: "l1",
              account_id: "a",
              account_code: "1000",
              account_name: "Cash",
              account_type: "asset",
              debit: "0",
              credit: "100",
              memo: null,
              division_id: null,
              line_number: 1,
            },
            {
              id: "l2",
              account_id: "b",
              account_code: "6000",
              account_name: "Utilities",
              account_type: "expense",
              debit: "100",
              credit: "0",
              memo: null,
              division_id: null,
              line_number: 2,
            },
          ],
        },
      ],
      next_cursor: null,
    });
    renderPage();
    expect(await screen.findByText("JE-00007")).toBeInTheDocument();
    expect(screen.getByText(/October utility/i)).toBeInTheDocument();
  });

  it("passes period_id filter to the API on selection", async () => {
    setOwner();
    const calls: string[] = [];
    mock.onGet("/api/v1/accounting/entries").reply((config) => {
      calls.push(
        new URLSearchParams(
          (config.params ?? {}) as Record<string, string>,
        ).toString(),
      );
      return [200, { items: [], next_cursor: null }];
    });
    renderPage();
    await screen.findByText(/no entries match/i);
    const select = screen.getByTestId("filter-period") as HTMLSelectElement;
    select.value = "p1";
    select.dispatchEvent(new Event("change", { bubbles: true }));
    await waitFor(() => {
      expect(calls.some((u) => u.includes("period_id=p1"))).toBe(true);
    });
  });
});
