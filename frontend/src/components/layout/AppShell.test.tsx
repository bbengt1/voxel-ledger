import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/layout/AppShell";
import { AppProviders } from "@/app/AppProviders";
import { useAuthStore } from "@/store/useAuthStore";

/** Force a phone-width matchMedia so the drawer (not the static sidebar) is active. */
function installMobileMatchMedia() {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: (query: string) => ({
      matches: false, // no min-width query is satisfied → below lg
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}

function renderShell(initial = "/jobs") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <AppProviders>
        <Routes>
          <Route path="/jobs" element={<AppShell>jobs page</AppShell>} />
          <Route path="/other" element={<AppShell>other page</AppShell>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<AppShell /> mobile drawer", () => {
  beforeEach(() => {
    installMobileMatchMedia();
    window.sessionStorage.clear();
    useAuthStore.getState().setSession({
      accessToken: "a",
      refreshToken: "r",
      user: { id: "u", email: "o@example.com", role: "owner" },
    });
  });

  afterEach(() => {
    // @ts-expect-error -- tear down the stub
    delete window.matchMedia;
    useAuthStore.getState().clearSession();
  });

  it("opens the nav drawer from the hamburger and closes it on Escape", async () => {
    const user = userEvent.setup();
    renderShell();

    // Drawer content is not mounted until opened.
    expect(screen.queryByTestId("nav-drawer")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("nav-menu-button"));
    expect(await screen.findByTestId("nav-drawer")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    await waitFor(() =>
      expect(screen.queryByTestId("nav-drawer")).not.toBeInTheDocument(),
    );
  });

  it("closes the drawer when navigating to a new route", async () => {
    const user = userEvent.setup();
    renderShell();

    await user.click(screen.getByTestId("nav-menu-button"));
    const drawer = await screen.findByTestId("nav-drawer");

    // Click a nav link inside the drawer → route changes → drawer closes.
    // (The home link is always present regardless of role/section.)
    await user.click(within(drawer).getByRole("link", { name: /voxel ledger home/i }));

    await waitFor(() =>
      expect(screen.queryByTestId("nav-drawer")).not.toBeInTheDocument(),
    );
  });
});
