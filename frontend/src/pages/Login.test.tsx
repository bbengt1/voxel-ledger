import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { LoginPage } from "@/pages/Login";
import { useAuthStore } from "@/store/useAuthStore";

function renderLogin(initialPath = "/login") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AppProviders>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div data-testid="home">home</div>} />
          <Route
            path="/dashboard"
            element={<div data-testid="dashboard">dashboard</div>}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<LoginPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
  });

  it("validates fields on submit", async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(
      await screen.findByText(/enter a valid email address/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/password is required/i)).toBeInTheDocument();
  });

  it("shows a generic error on 401 without revealing which field is wrong", async () => {
    mock.onPost("/api/v1/auth/login").reply(401, { detail: "bad creds" });
    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByLabelText(/email/i), "user@example.com");
    await user.type(screen.getByLabelText(/password/i), "hunter2");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    const err = await screen.findByTestId("login-error");
    // Generic message; the same string is shown regardless of which field
    // was wrong, to avoid account-enumeration via differential errors.
    expect(err).toHaveTextContent("Invalid email or password.");
    // Field-level zod errors must NOT appear.
    expect(
      screen.queryByText(/enter a valid email address/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/password is required/i),
    ).not.toBeInTheDocument();
  });

  it("navigates to ?next= on success and stores the session", async () => {
    mock.onPost("/api/v1/auth/login").reply(200, {
      access_token: "at-1",
      refresh_token: "rt-1",
      expires_in: 900,
      token_type: "bearer",
    });
    mock.onGet("/api/v1/auth/me").reply(200, {
      id: "user-1",
      email: "user@example.com",
      full_name: "User One",
      is_active: true,
      role: "owner",
    });

    const user = userEvent.setup();
    renderLogin("/login?next=%2Fdashboard");

    await user.type(screen.getByLabelText(/email/i), "user@example.com");
    await user.type(screen.getByLabelText(/password/i), "hunter2");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByTestId("dashboard")).toBeInTheDocument();
    });
    expect(useAuthStore.getState().accessToken).toBe("at-1");
    expect(useAuthStore.getState().user?.email).toBe("user@example.com");
  });

  it("defaults to / when no next param", async () => {
    mock.onPost("/api/v1/auth/login").reply(200, {
      access_token: "at-2",
      refresh_token: "rt-2",
      expires_in: 900,
      token_type: "bearer",
    });
    mock.onGet("/api/v1/auth/me").reply(200, {
      id: "user-1",
      email: "user@example.com",
      full_name: "User One",
      is_active: true,
      role: "owner",
    });

    const user = userEvent.setup();
    renderLogin("/login");

    await user.type(screen.getByLabelText(/email/i), "user@example.com");
    await user.type(screen.getByLabelText(/password/i), "hunter2");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByTestId("home")).toBeInTheDocument();
    });
  });
});
