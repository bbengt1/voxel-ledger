import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { UserCreatePage } from "@/pages/admin/UserCreate";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/admin/users/new"]}>
      <AppProviders>
        <Routes>
          <Route path="/admin/users/new" element={<UserCreatePage />} />
          <Route
            path="/admin/users/:id"
            element={<div data-testid="detail-page">detail</div>}
          />
          <Route
            path="/admin/users"
            element={<div data-testid="list-page">list</div>}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<UserCreatePage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    setOwner();
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
  });

  it("submits the form and shows the generated password modal", async () => {
    mock.onPost("/api/v1/users").reply(201, {
      user: {
        id: "33333333-3333-3333-3333-333333333333",
        email: "fresh@example.com",
        full_name: "Fresh",
        role: "bookkeeper",
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        last_login: null,
      },
      generated_password: "PASSWORD-ONCE-1!aA",
    });

    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/email/i), "fresh@example.com");
    await user.type(screen.getByLabelText(/full name/i), "Fresh");
    await user.selectOptions(screen.getByLabelText(/role/i), "bookkeeper");
    await user.click(screen.getByRole("button", { name: /create user/i }));

    expect(await screen.findByTestId("generated-password")).toHaveTextContent(
      "PASSWORD-ONCE-1!aA",
    );
  });

  it("shows 'Copied' after clicking copy-to-clipboard", async () => {
    mock.onPost("/api/v1/users").reply(201, {
      user: {
        id: "x",
        email: "x@example.com",
        full_name: "x",
        role: "sales",
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        last_login: null,
      },
      generated_password: "ClipMe-1!",
    });

    const writeText = vi.fn().mockResolvedValue(undefined);

    renderPage();
    // userEvent.setup() reinstalls a stub clipboard, so patch AFTER it
    // and rely on Object.defineProperty to win.
    const user = userEvent.setup({ writeToClipboard: false });
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    await user.type(screen.getByLabelText(/email/i), "x@example.com");
    await user.type(screen.getByLabelText(/full name/i), "X");
    await user.click(screen.getByRole("button", { name: /create user/i }));

    await screen.findByTestId("generated-password");
    await user.click(screen.getByRole("button", { name: /copy to clipboard/i }));
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /copied/i }),
      ).toBeInTheDocument();
    });
    expect(writeText).toHaveBeenCalledWith("ClipMe-1!");
  });

  it("warns if the user tries to close without acknowledging", async () => {
    mock.onPost("/api/v1/users").reply(201, {
      user: {
        id: "y",
        email: "y@example.com",
        full_name: "y",
        role: "sales",
        is_active: true,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        last_login: null,
      },
      generated_password: "Once-1!",
    });

    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/email/i), "y@example.com");
    await user.type(screen.getByLabelText(/full name/i), "Y");
    await user.click(screen.getByRole("button", { name: /create user/i }));

    await screen.findByTestId("generated-password");
    // Try to close without ticking the box.
    await user.click(screen.getByRole("button", { name: /^done$/i }));
    expect(screen.getByTestId("save-warning")).toBeInTheDocument();

    // Acknowledge and close.
    await user.click(screen.getByTestId("close-anyway"));
    await waitFor(() => {
      expect(screen.queryByTestId("generated-password")).not.toBeInTheDocument();
    });
  });

  it("shows server error detail on 400", async () => {
    mock.onPost("/api/v1/users").reply(400, { detail: "email already exists" });
    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/email/i), "dup@example.com");
    await user.type(screen.getByLabelText(/full name/i), "Dup");
    await user.click(screen.getByRole("button", { name: /create user/i }));
    expect(await screen.findByTestId("create-error")).toHaveTextContent(
      /already exists/i,
    );
  });
});
