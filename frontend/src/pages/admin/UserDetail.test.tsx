import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { UserDetailPage } from "@/pages/admin/UserDetail";
import { useAuthStore } from "@/store/useAuthStore";

const USER_ID = "44444444-4444-4444-4444-444444444444";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function activeUser() {
  return {
    id: USER_ID,
    email: "u@example.com",
    full_name: "User",
    role: "sales" as const,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    last_login: null,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/admin/users/${USER_ID}`]}>
      <AppProviders>
        <Routes>
          <Route path="/admin/users/:id" element={<UserDetailPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<UserDetailPage />", () => {
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

  it("loads, edits, and saves", async () => {
    mock.onGet(`/api/v1/users/${USER_ID}`).reply(200, activeUser());
    let observedBody: Record<string, unknown> | undefined;
    mock.onPatch(`/api/v1/users/${USER_ID}`).reply((config) => {
      observedBody = JSON.parse(config.data ?? "{}");
      return [
        200,
        { ...activeUser(), full_name: "Renamed", role: "production" },
      ];
    });

    renderPage();
    await screen.findByDisplayValue("User");
    const user = userEvent.setup();
    const nameInput = screen.getByDisplayValue("User");
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed");
    await user.selectOptions(screen.getByDisplayValue("sales"), "production");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => {
      expect(screen.getByTestId("save-msg")).toHaveTextContent("Saved");
    });
    expect(observedBody).toMatchObject({
      full_name: "Renamed",
      role: "production",
    });
  });

  it("deactivates with a confirm dialog", async () => {
    mock.onGet(`/api/v1/users/${USER_ID}`).reply(200, activeUser());
    mock.onPost(`/api/v1/users/${USER_ID}/deactivate`).reply(200, {
      ...activeUser(),
      is_active: false,
    });

    renderPage();
    await screen.findByText("u@example.com");
    const user = userEvent.setup();
    await user.click(screen.getByTestId("deactivate-btn"));
    // Confirm dialog visible.
    expect(
      await screen.findByText(/deactivate u@example\.com\?/i),
    ).toBeInTheDocument();
    await user.click(screen.getByTestId("confirm-deactivate"));

    await waitFor(() => {
      expect(screen.getByText(/inactive/i)).toBeInTheDocument();
    });
  });

  it("reset password flow opens a modal with the new password", async () => {
    mock.onGet(`/api/v1/users/${USER_ID}`).reply(200, activeUser());
    mock
      .onPost(`/api/v1/users/${USER_ID}/reset-password`)
      .reply(200, { user_id: USER_ID, generated_password: "Newpw-1!aA" });

    renderPage();
    await screen.findByText("u@example.com");
    const user = userEvent.setup();
    await user.click(screen.getByTestId("reset-pwd-btn"));
    await user.click(screen.getByTestId("confirm-reset"));

    expect(await screen.findByTestId("generated-password")).toHaveTextContent(
      "Newpw-1!aA",
    );
  });
});
