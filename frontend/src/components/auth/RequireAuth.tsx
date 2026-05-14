import { type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuthStore } from "@/store/useAuthStore";

/**
 * Route guard. If there is no access token in the auth store, redirects to
 * `/login?next=<encoded current path>` so post-login navigation can return
 * the user to where they were headed.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const location = useLocation();

  if (!accessToken) {
    const next = location.pathname + location.search;
    return (
      <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />
    );
  }

  return <>{children}</>;
}
