import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { ApprovalsListPage } from "@/pages/approvals/ApprovalsList";
import { useAuthStore } from "@/store/useAuthStore";

function setSession(role: "owner" | "bookkeeper" | "sales") {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u-self", email: `${role}@x.com`, role },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/approvals"]}>
      <AppProviders>
        <Routes>
          <Route path="/approvals" element={<ApprovalsListPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

const sampleRow = {
  id: "11111111-1111-1111-1111-111111111111",
  request_type: "accounting.large_journal_entry",
  subject_kind: "journal_entry",
  subject_id: "22222222-2222-2222-2222-222222222222",
  requested_by_user_id: "u-self",
  requested_at: "2026-05-14T00:00:00Z",
  state: "pending" as const,
  threshold_amount: "1000.00",
};

describe("<ApprovalsListPage />", () => {
  let mock: MockAdapter;
  beforeEach(() => {
    useAuthStore.getState().clearSession();
    mock = new MockAdapter(apiClient);
  });
  afterEach(() => mock.restore());

  it("renders rows from the API", async () => {
    setSession("owner");
    mock.onGet("/api/v1/approvals").reply(200, {
      items: [sampleRow],
      next_cursor: null,
    });
    renderPage();
    expect(
      await screen.findByText("accounting.large_journal_entry"),
    ).toBeInTheDocument();
    expect(screen.getByText(/journal_entry:/)).toBeInTheDocument();
  });

  it("re-queries when the state filter changes", async () => {
    setSession("owner");
    const requested: Record<string, string>[] = [];
    mock.onGet("/api/v1/approvals").reply((config) => {
      requested.push((config.params ?? {}) as Record<string, string>);
      return [200, { items: [], next_cursor: null }];
    });
    renderPage();
    await waitFor(() => expect(requested.length).toBeGreaterThan(0));
    await userEvent.selectOptions(screen.getByTestId("state-filter"), "approved");
    await waitFor(() =>
      expect(requested.some((p) => p.state === "approved")).toBe(true),
    );
  });

  it("renders empty-state message when no items", async () => {
    setSession("sales");
    mock.onGet("/api/v1/approvals").reply(200, {
      items: [],
      next_cursor: null,
    });
    renderPage();
    expect(await screen.findByTestId("empty")).toBeInTheDocument();
  });
});
