import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { DivisionsListPage } from "@/pages/accounting/DivisionsList";
import { useAuthStore } from "@/store/useAuthStore";

function setRole(role: "owner" | "bookkeeper") {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "x@x.com", role },
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AppProviders>
        <DivisionsListPage />
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<DivisionsListPage />", () => {
  let mock: MockAdapter;
  beforeEach(() => {
    useAuthStore.getState().clearSession();
    mock = new MockAdapter(apiClient);
  });
  afterEach(() => mock.restore());

  it("creates a division through the modal (owner)", async () => {
    setRole("owner");
    const items = [
      {
        id: "d1",
        code: "PROD",
        name: "Production",
        is_archived: false,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ];
    mock
      .onGet("/api/v1/accounting/divisions")
      .reply(200, { items, next_cursor: null });
    let postCalls = 0;
    mock.onPost("/api/v1/accounting/divisions").reply((config) => {
      postCalls++;
      const body = JSON.parse(config.data as string);
      expect(body.code).toBe("MKT");
      return [
        201,
        {
          id: "d2",
          code: body.code,
          name: body.name,
          is_archived: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ];
    });
    renderPage();
    await screen.findByText("Production");
    await userEvent.click(screen.getByTestId("open-new-division"));
    await userEvent.type(screen.getByTestId("new-division-code"), "MKT");
    await userEvent.type(screen.getByTestId("new-division-name"), "Marketing");
    await userEvent.click(screen.getByTestId("submit-new-division"));
    await waitFor(() => expect(postCalls).toBe(1));
  });

  it("hides write actions for non-owner roles", async () => {
    setRole("bookkeeper");
    mock
      .onGet("/api/v1/accounting/divisions")
      .reply(200, { items: [], next_cursor: null });
    renderPage();
    await waitFor(() =>
      expect(screen.queryByTestId("open-new-division")).not.toBeInTheDocument(),
    );
  });
});
