import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { App } from "@/App";
import { AppProviders } from "@/app/AppProviders";
import { useAuthStore } from "@/store/useAuthStore";

describe("<App />", () => {
  afterEach(() => {
    useAuthStore.getState().clearSession();
  });

  it("redirects to /login when visiting / unauthenticated", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppProviders>
          <App />
        </AppProviders>
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { name: /sign in/i }),
    ).toBeInTheDocument();
  });

  it("renders the home screen on / when authenticated", () => {
    useAuthStore.getState().setSession({
      accessToken: "at",
      refreshToken: "rt",
      user: { id: "u1", email: "user@example.com", role: "owner" },
    });

    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppProviders>
          <App />
        </AppProviders>
      </MemoryRouter>,
    );

    expect(screen.getByTestId("home-screen")).toBeInTheDocument();
  });
});
