import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { Sidebar } from "@/components/layout/Sidebar";
import { useAuthStore, type Role } from "@/store/useAuthStore";

function withRole(role: Role | null) {
  if (role === null) {
    useAuthStore.getState().clearSession();
    return;
  }
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: `${role}@example.com`, role },
  });
}

function renderSidebar() {
  return render(
    <MemoryRouter>
      <Sidebar />
    </MemoryRouter>,
  );
}

describe("<Sidebar /> admin gating", () => {
  beforeEach(() => {
    useAuthStore.getState().clearSession();
  });

  it.each<Role>(["owner", "bookkeeper"])(
    "shows Users link for %s",
    (role) => {
      withRole(role);
      renderSidebar();
      expect(screen.getByRole("link", { name: /users/i })).toBeInTheDocument();
    },
  );

  it.each<Role>(["production", "sales", "viewer"])(
    "hides Admin section for %s",
    (role) => {
      withRole(role);
      renderSidebar();
      expect(screen.queryByText(/admin/i)).not.toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: /users/i }),
      ).not.toBeInTheDocument();
    },
  );

  it("hides Admin section when unauthenticated", () => {
    withRole(null);
    renderSidebar();
    expect(screen.queryByText(/admin/i)).not.toBeInTheDocument();
  });
});
