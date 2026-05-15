import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { AccountsTreePage } from "@/pages/accounting/AccountsTree";
import { useAuthStore } from "@/store/useAuthStore";

const PARENT_ID = "11111111-1111-1111-1111-111111111111";
const CHILD_ID = "22222222-2222-2222-2222-222222222222";

function setRole(role: "owner" | "bookkeeper" | "viewer") {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "u@x.com", role },
  });
}

function tree() {
  return {
    items: [
      {
        id: PARENT_ID,
        code: "1000",
        name: "Assets",
        type: "asset" as const,
        description: null,
        parent_account_id: null,
        is_archived: false,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        children: [
          {
            id: CHILD_ID,
            code: "1100",
            name: "Cash",
            type: "asset" as const,
            description: null,
            parent_account_id: PARENT_ID,
            is_archived: false,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
            children: [],
          },
        ],
      },
    ],
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AppProviders>
        <AccountsTreePage />
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<AccountsTreePage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => mock.restore());

  it("renders the tree and expands/collapses a node", async () => {
    setRole("owner");
    mock.onGet("/api/v1/accounts/tree").reply(200, tree());
    renderPage();
    expect(await screen.findByText("Assets")).toBeInTheDocument();
    // child is visible because tree auto-expands top-level on first load.
    expect(screen.getByText("Cash")).toBeInTheDocument();
    // Collapse the parent.
    await userEvent.click(screen.getByTestId(`account-toggle-${PARENT_ID}`));
    expect(screen.queryByText("Cash")).not.toBeInTheDocument();
  });

  it("opens the New account modal and seeds parent type from selection", async () => {
    setRole("owner");
    mock.onGet("/api/v1/accounts/tree").reply(200, tree());
    mock.onGet(new RegExp(`/api/v1/accounts/${PARENT_ID}$`)).reply(200, {
      id: PARENT_ID,
      code: "1000",
      name: "Assets",
      type: "asset",
      description: null,
      parent_account_id: null,
      is_archived: false,
      parent_chain: [],
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    mock
      .onGet("/api/v1/accounting/account-balances")
      .reply(200, { items: [], next_cursor: null });
    renderPage();
    await screen.findByText("Assets");
    await userEvent.click(screen.getByTestId(`account-select-${PARENT_ID}`));
    await userEvent.click(screen.getByTestId("open-new-account"));
    expect(await screen.findByTestId("new-account-dialog")).toBeInTheDocument();
    const typeSelect = screen.getByTestId("new-type") as HTMLSelectElement;
    expect(typeSelect.value).toBe("asset");
    expect(typeSelect).toBeDisabled();
  });

  it("hides New account button for viewer role", async () => {
    setRole("viewer");
    mock.onGet("/api/v1/accounts/tree").reply(200, tree());
    renderPage();
    await screen.findByText("Assets");
    await waitFor(() =>
      expect(screen.queryByTestId("open-new-account")).not.toBeInTheDocument(),
    );
  });
});
