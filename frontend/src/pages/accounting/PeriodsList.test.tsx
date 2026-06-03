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
    expect((await screen.findAllByTestId("close-p1")).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryAllByTestId("lock-p1")).toHaveLength(0);
    expect(screen.queryAllByTestId("reopen-p1")).toHaveLength(0);
  });

  it("renders reopen + lock for a closed period (owner)", async () => {
    setRole("owner");
    mock.onGet("/api/v1/accounting/periods").reply(200, {
      items: [period({ state: "closed" })],
      next_cursor: null,
    });
    renderPage();
    expect((await screen.findAllByTestId("reopen-p1")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByTestId("lock-p1").length).toBeGreaterThanOrEqual(1);
  });

  it("renders reopen but not lock for closed (bookkeeper, no lock)", async () => {
    setRole("bookkeeper");
    mock.onGet("/api/v1/accounting/periods").reply(200, {
      items: [period({ state: "closed" })],
      next_cursor: null,
    });
    renderPage();
    expect((await screen.findAllByTestId("reopen-p1")).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryAllByTestId("lock-p1")).toHaveLength(0);
  });

  it("renders no actions for a locked period", async () => {
    setRole("owner");
    mock.onGet("/api/v1/accounting/periods").reply(200, {
      items: [period({ state: "locked", locked_at: "2026-04-01T00:00:00Z" })],
      next_cursor: null,
    });
    renderPage();
    await screen.findAllByText("2026-Q1");
    expect(screen.queryAllByTestId("close-p1")).toHaveLength(0);
    expect(screen.queryAllByTestId("reopen-p1")).toHaveLength(0);
    expect(screen.queryAllByTestId("lock-p1")).toHaveLength(0);
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
    await userEvent.click((await screen.findAllByTestId("lock-p1"))[0]!);
    expect(await screen.findByTestId("lock-dialog")).toHaveTextContent(
      /permanent/i,
    );
    expect(postCalls).toBe(0);
    await userEvent.click(screen.getByTestId("confirm-lock"));
    await waitFor(() => expect(postCalls).toBe(1));
  });
});
