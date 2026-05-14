import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { UsersListPage } from "@/pages/admin/UsersList";
import { useAuthStore } from "@/store/useAuthStore";

function setOwnerSession() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "owner@example.com", role: "owner" },
  });
}

function setBookkeeperSession() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "bk@example.com", role: "bookkeeper" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/admin/users"]}>
      <AppProviders>
        <Routes>
          <Route path="/admin/users" element={<UsersListPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<UsersListPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders rows from the API", async () => {
    setOwnerSession();
    mock.onGet("/users").reply(200, {
      items: [
        {
          id: "11111111-1111-1111-1111-111111111111",
          email: "alice@example.com",
          full_name: "Alice",
          role: "sales",
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          last_login: null,
        },
      ],
      next_cursor: null,
    });
    renderPage();
    expect(await screen.findByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("debounces search input and re-queries with search param", async () => {
    setOwnerSession();
    mock.onGet("/users").reply((config) => {
      const params = config.params as Record<string, string> | undefined;
      if (params?.["search"] === "bob") {
        return [
          200,
          {
            items: [
              {
                id: "22222222-2222-2222-2222-222222222222",
                email: "bob@example.com",
                full_name: "Bob",
                role: "sales",
                is_active: true,
                created_at: "2026-01-01T00:00:00Z",
                updated_at: "2026-01-01T00:00:00Z",
                last_login: null,
              },
            ],
            next_cursor: null,
          },
        ];
      }
      return [200, { items: [], next_cursor: null }];
    });

    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/search/i), "bob");
    await waitFor(
      () => {
        expect(screen.getByText("bob@example.com")).toBeInTheDocument();
      },
      { timeout: 1500 },
    );
  });

  it("applies role filter as a query param", async () => {
    setOwnerSession();
    let observedRole: string | undefined;
    mock.onGet("/users").reply((config) => {
      const params = config.params as Record<string, string> | undefined;
      observedRole = params?.["role"];
      return [200, { items: [], next_cursor: null }];
    });
    renderPage();
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText(/role/i), "bookkeeper");
    await waitFor(() => {
      expect(observedRole).toBe("bookkeeper");
    });
  });

  it("advances the pagination cursor on Load more", async () => {
    setOwnerSession();
    let requestCount = 0;
    let observedCursor: string | undefined;
    mock.onGet("/users").reply((config) => {
      requestCount += 1;
      const params = config.params as Record<string, string> | undefined;
      observedCursor = params?.["cursor"];
      if (requestCount === 1) {
        return [
          200,
          {
            items: [
              {
                id: "a",
                email: "a@example.com",
                full_name: "A",
                role: "sales",
                is_active: true,
                created_at: "2026-01-01T00:00:00Z",
                updated_at: "2026-01-01T00:00:00Z",
                last_login: null,
              },
            ],
            next_cursor: "cursor-1",
          },
        ];
      }
      return [200, { items: [], next_cursor: null }];
    });

    renderPage();
    const user = userEvent.setup();
    await screen.findByText("a@example.com");
    await user.click(screen.getByTestId("load-more"));
    await waitFor(() => {
      expect(observedCursor).toBe("cursor-1");
    });
  });

  it("hides the New user button for bookkeepers", async () => {
    setBookkeeperSession();
    mock.onGet("/users").reply(200, { items: [], next_cursor: null });
    renderPage();
    await waitFor(() => {
      expect(
        screen.queryByRole("link", { name: /new user/i }),
      ).not.toBeInTheDocument();
    });
  });
});
