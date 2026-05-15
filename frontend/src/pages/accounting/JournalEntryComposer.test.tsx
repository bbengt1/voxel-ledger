import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { JournalEntryComposerPage } from "@/pages/accounting/JournalEntryComposer";
import { useAuthStore } from "@/store/useAuthStore";

const ACC_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const ACC_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@x.com", role: "owner" },
  });
}

function accountItem(id: string, code: string, name: string) {
  return {
    id,
    code,
    name,
    type: "asset" as const,
    description: null,
    parent_account_id: null,
    is_archived: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/accounting/entries/new"]}>
      <AppProviders>
        <Routes>
          <Route
            path="/accounting/entries/new"
            element={<JournalEntryComposerPage />}
          />
          <Route
            path="/accounting/entries/:id"
            element={<div data-testid="detail-page">detail</div>}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

async function pickAccountInLine(idx: number, code: string) {
  const input = screen.getByTestId(`line-${idx}-account-input`);
  await userEvent.click(input);
  // Wait for the dropdown to populate.
  await waitFor(() =>
    expect(
      screen.queryByTestId(`line-${idx}-account-options`),
    ).toBeInTheDocument(),
  );
  // Click the matching option (first option that contains the code).
  const buttons = await screen.findAllByRole("button");
  const match = buttons.find((b) => b.textContent?.includes(code));
  if (!match) throw new Error(`no option with code ${code}`);
  await userEvent.click(match);
}

describe("<JournalEntryComposerPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock
      .onGet("/api/v1/accounting/divisions")
      .reply(200, { items: [], next_cursor: null });
    mock.onGet("/api/v1/accounts").reply(200, {
      items: [
        accountItem(ACC_A, "1000", "Cash"),
        accountItem(ACC_B, "6000", "Rent expense"),
      ],
      next_cursor: null,
    });
  });

  afterEach(() => mock.restore());

  it("submit is disabled until lines balance and accounts are picked", async () => {
    setOwner();
    renderPage();
    const submit = await screen.findByTestId("submit-entry");
    expect(submit).toBeDisabled();

    await userEvent.type(
      screen.getByTestId("entry-description"),
      "October rent",
    );
    await userEvent.type(screen.getByTestId("line-0-debit"), "100");
    await userEvent.type(screen.getByTestId("line-1-credit"), "100");

    // Still disabled — no accounts picked.
    expect(submit).toBeDisabled();
    expect(screen.getByTestId("difference").textContent).toBe("0.00");

    await pickAccountInLine(0, "6000");
    await pickAccountInLine(1, "1000");

    await waitFor(() =>
      expect(screen.getByTestId("submit-entry")).not.toBeDisabled(),
    );
  });

  it("navigates to detail on 201", async () => {
    setOwner();
    mock.onPost("/api/v1/accounting/entries").reply(201, {
      id: "entry-1",
      entry_number: "JE-00001",
      description: "x",
      posted_at: "2026-05-15T00:00:00Z",
      period_id: "p",
      actor_user_id: "u",
      is_reversed: false,
      reversal_of_entry_id: null,
      created_at: "2026-05-15T00:00:00Z",
      lines: [],
    });
    renderPage();
    await userEvent.type(
      screen.getByTestId("entry-description"),
      "October rent",
    );
    await userEvent.type(screen.getByTestId("line-0-debit"), "50");
    await userEvent.type(screen.getByTestId("line-1-credit"), "50");
    await pickAccountInLine(0, "6000");
    await pickAccountInLine(1, "1000");
    await userEvent.click(screen.getByTestId("submit-entry"));
    expect(await screen.findByTestId("detail-page")).toBeInTheDocument();
  });

  it("renders the approval banner on 202", async () => {
    setOwner();
    mock.onPost("/api/v1/accounting/entries").reply(202, {
      status: "pending_approval",
      approval_request_id: "approval-1",
    });
    renderPage();
    await userEvent.type(screen.getByTestId("entry-description"), "huge");
    await userEvent.type(screen.getByTestId("line-0-debit"), "5000");
    await userEvent.type(screen.getByTestId("line-1-credit"), "5000");
    await pickAccountInLine(0, "6000");
    await pickAccountInLine(1, "1000");
    await userEvent.click(screen.getByTestId("submit-entry"));
    expect(await screen.findByTestId("approval-banner")).toBeInTheDocument();
    expect(screen.getByTestId("approval-link")).toHaveAttribute(
      "href",
      "/approvals/approval-1",
    );
  });

  it("renders backend detail inline on 400", async () => {
    setOwner();
    mock
      .onPost("/api/v1/accounting/entries")
      .reply(400, { detail: "period is closed" });
    renderPage();
    await userEvent.type(screen.getByTestId("entry-description"), "x");
    await userEvent.type(screen.getByTestId("line-0-debit"), "1");
    await userEvent.type(screen.getByTestId("line-1-credit"), "1");
    await pickAccountInLine(0, "6000");
    await pickAccountInLine(1, "1000");
    await userEvent.click(screen.getByTestId("submit-entry"));
    expect(await screen.findByTestId("composer-error")).toHaveTextContent(
      /period is closed/i,
    );
  });
});
