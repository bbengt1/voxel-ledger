import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { TransferFormPage } from "@/pages/banking/TransferForm";
import { useAuthStore } from "@/store/useAuthStore";

const A_ID = "11111111-1111-1111-1111-111111111111";
const B_ID = "22222222-2222-2222-2222-222222222222";
const JE_ID = "33333333-3333-3333-3333-333333333333";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/banking/transfer"]}>
      <AppProviders>
        <Routes>
          <Route path="/banking/transfer" element={<TransferFormPage />} />
          <Route
            path="/accounting/entries/:id"
            element={<div>je-detail</div>}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<TransferFormPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/accounts").reply(200, {
      items: [
        {
          id: A_ID,
          code: "1010",
          name: "Checking",
          type: "asset",
          is_archived: false,
          parent_account_id: null,
          description: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
        {
          id: B_ID,
          code: "1020",
          name: "Savings",
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

  it("blocks from == to", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("transfer-from")).toBeInTheDocument(),
    );
    await user.selectOptions(screen.getByTestId("transfer-from"), A_ID);
    await user.selectOptions(screen.getByTestId("transfer-to"), A_ID);
    await user.type(screen.getByTestId("transfer-amount"), "10");
    await user.click(screen.getByTestId("transfer-submit"));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/different/i),
    );
  });

  it("submits the request shape", async () => {
    const user = userEvent.setup();
    let body: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/inter-account-transfers").reply((config) => {
      body = JSON.parse(config.data as string);
      return [201, { journal_entry_id: JE_ID }];
    });

    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("transfer-from")).toBeInTheDocument(),
    );
    await user.selectOptions(screen.getByTestId("transfer-from"), A_ID);
    await user.selectOptions(screen.getByTestId("transfer-to"), B_ID);
    await user.clear(screen.getByTestId("transfer-amount"));
    await user.type(screen.getByTestId("transfer-amount"), "25.50");
    await user.click(screen.getByTestId("transfer-submit"));

    await waitFor(() => expect(body).toBeDefined());
    expect(body?.["from_account_id"]).toBe(A_ID);
    expect(body?.["to_account_id"]).toBe(B_ID);
    expect(body?.["amount"]).toBe("25.5");
    expect(typeof body?.["occurred_at"]).toBe("string");
  });
});
