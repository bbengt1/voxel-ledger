import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { JournalEntryDetailPage } from "@/pages/accounting/JournalEntryDetail";
import { useAuthStore } from "@/store/useAuthStore";

const ID = "11111111-1111-1111-1111-111111111111";

function setRole(role: "owner" | "bookkeeper" | "sales") {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "x@x.com", role },
  });
}

function entry(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: ID,
    entry_number: "JE-1",
    description: "rent",
    posted_at: "2026-05-15T00:00:00Z",
    period_id: "p1",
    actor_user_id: "u",
    is_reversed: false,
    reversal_of_entry_id: null,
    created_at: "2026-05-15T00:00:00Z",
    lines: [
      {
        id: "l1",
        account_id: "a",
        account_code: "6000",
        account_name: "Rent",
        account_type: "expense",
        debit: "100",
        credit: "0",
        memo: null,
        division_id: null,
        line_number: 1,
      },
      {
        id: "l2",
        account_id: "b",
        account_code: "1000",
        account_name: "Cash",
        account_type: "asset",
        debit: "0",
        credit: "100",
        memo: null,
        division_id: null,
        line_number: 2,
      },
    ],
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/accounting/entries/${ID}`]}>
      <AppProviders>
        <Routes>
          <Route
            path="/accounting/entries/:id"
            element={<JournalEntryDetailPage />}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<JournalEntryDetailPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => mock.restore());

  it("requires confirmation to reverse an entry", async () => {
    setRole("owner");
    mock.onGet(`/api/v1/accounting/entries/${ID}`).reply(200, entry());
    let postCalled = 0;
    mock.onPost(`/api/v1/accounting/entries/${ID}/reverse`).reply(() => {
      postCalled++;
      return [201, entry({ is_reversed: true })];
    });
    renderPage();
    await screen.findByText(/JE-1/i);
    await userEvent.click(screen.getByTestId("reverse-entry"));
    expect(await screen.findByTestId("reverse-dialog")).toBeInTheDocument();
    expect(postCalled).toBe(0);
    await userEvent.click(screen.getByTestId("confirm-reverse"));
    await waitFor(() => expect(postCalled).toBe(1));
  });

  it("disables reverse when entry is already reversed", async () => {
    setRole("owner");
    mock
      .onGet(`/api/v1/accounting/entries/${ID}`)
      .reply(200, entry({ is_reversed: true }));
    renderPage();
    await screen.findByText(/JE-1/i);
    expect(screen.getByTestId("reverse-entry")).toBeDisabled();
  });

  it("disables reverse when entry is itself a reversal", async () => {
    setRole("owner");
    mock
      .onGet(`/api/v1/accounting/entries/${ID}`)
      .reply(200, entry({ reversal_of_entry_id: "prior-id" }));
    renderPage();
    await screen.findByText(/JE-1/i);
    expect(screen.getByTestId("reverse-entry")).toBeDisabled();
  });

  it("disables reverse for sales role", async () => {
    setRole("sales");
    mock.onGet(`/api/v1/accounting/entries/${ID}`).reply(200, entry());
    renderPage();
    await screen.findByText(/JE-1/i);
    expect(screen.getByTestId("reverse-entry")).toBeDisabled();
  });
});
