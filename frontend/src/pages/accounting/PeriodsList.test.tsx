import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { PeriodsListPage } from "@/pages/accounting/PeriodsList";
import { useAuthStore } from "@/store/useAuthStore";

function setRole(role: "owner" | "bookkeeper" | "sales") {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "x@x.com", role },
  });
}

function period(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "p1",
    name: "2026-Q1",
    start_date: "2026-01-01",
    end_date: "2026-03-31",
    state: "open" as "open" | "closed" | "locked",
    closed_at: null,
    closed_by_user_id: null,
    locked_at: null,
    locked_by_user_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AppProviders>
        <PeriodsListPage />
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<PeriodsListPage />", () => {
  let mock: MockAdapter;
  beforeEach(() => {
    useAuthStore.getState().clearSession();
    mock = new MockAdapter(apiClient);
  });
  afterEach(() => mock.restore());

  it("renders the close action for an open period (owner)", async () => {
    setRole("owner");
    mock
      .onGet("/api/v1/accounting/periods")
      .reply(200, { items: [period()], next_cursor: null });
    renderPage();
    expect(await screen.findByTestId("close-p1")).toBeInTheDocument();
    expect(screen.queryByTestId("lock-p1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("reopen-p1")).not.toBeInTheDocument();
  });

  it("renders reopen + lock for a closed period (owner)", async () => {
    setRole("owner");
    mock.onGet("/api/v1/accounting/periods").reply(200, {
      items: [period({ state: "closed" })],
      next_cursor: null,
    });
    renderPage();
    expect(await screen.findByTestId("reopen-p1")).toBeInTheDocument();
    expect(screen.getByTestId("lock-p1")).toBeInTheDocument();
  });

  it("renders reopen but not lock for closed (bookkeeper, no lock)", async () => {
    setRole("bookkeeper");
    mock.onGet("/api/v1/accounting/periods").reply(200, {
      items: [period({ state: "closed" })],
      next_cursor: null,
    });
    renderPage();
    expect(await screen.findByTestId("reopen-p1")).toBeInTheDocument();
    expect(screen.queryByTestId("lock-p1")).not.toBeInTheDocument();
  });

  it("renders no actions for a locked period", async () => {
    setRole("owner");
    mock.onGet("/api/v1/accounting/periods").reply(200, {
      items: [period({ state: "locked", locked_at: "2026-04-01T00:00:00Z" })],
      next_cursor: null,
    });
    renderPage();
    await screen.findByText("2026-Q1");
    expect(screen.queryByTestId("close-p1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("reopen-p1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("lock-p1")).not.toBeInTheDocument();
  });

  it("shows a confirmation dialog before locking", async () => {
    setRole("owner");
    mock.onGet("/api/v1/accounting/periods").reply(200, {
      items: [period({ state: "closed" })],
      next_cursor: null,
    });
    let postCalls = 0;
    mock.onPost("/api/v1/accounting/periods/p1/lock").reply(() => {
      postCalls++;
      return [200, period({ state: "locked" })];
    });
    renderPage();
    await userEvent.click(await screen.findByTestId("lock-p1"));
    expect(await screen.findByTestId("lock-dialog")).toHaveTextContent(
      /permanent/i,
    );
    expect(postCalls).toBe(0);
    await userEvent.click(screen.getByTestId("confirm-lock"));
    await waitFor(() => expect(postCalls).toBe(1));
  });
});
