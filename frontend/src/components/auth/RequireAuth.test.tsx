import { render, screen } from "@testing-library/react";
import {
  MemoryRouter,
  Route,
  Routes,
  useSearchParams,
} from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { RequireAuth } from "@/components/auth/RequireAuth";
import { useAuthStore } from "@/store/useAuthStore";

function RouterProbe({ testid }: { testid: string }) {
  const [params] = useSearchParams();
  return <div data-testid={testid} data-next={params.get("next") ?? ""} />;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<RouterProbe testid="login" />} />
        <Route
          path="/protected"
          element={
            <RequireAuth>
              <div data-testid="protected">protected</div>
            </RequireAuth>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("<RequireAuth />", () => {
  afterEach(() => {
    useAuthStore.getState().clearSession();
  });

  it("redirects to /login when no access token", () => {
    renderAt("/protected?tab=open");
    expect(screen.getByTestId("login")).toBeInTheDocument();
    expect(screen.queryByTestId("protected")).not.toBeInTheDocument();
  });

  it("preserves the original URL as ?next=", () => {
    renderAt("/protected?tab=open");
    expect(screen.getByTestId("login")).toHaveAttribute(
      "data-next",
      "/protected?tab=open",
    );
  });

  it("renders children when an access token is present", () => {
    useAuthStore.getState().setSession({
      accessToken: "at",
      refreshToken: "rt",
      user: { id: "u", email: "e@e.com", role: "owner" },
    });
    renderAt("/protected");
    expect(screen.getByTestId("protected")).toBeInTheDocument();
  });
});
