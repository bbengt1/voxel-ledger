import { useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import { Button } from "@/components/ui/Button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import { Input } from "@/components/ui/Input";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { useAuthStore } from "@/store/useAuthStore";

export function TopBar() {
  const user = useAuthStore((s) => s.user);
  const refreshToken = useAuthStore((s) => s.refreshToken);
  const clearSession = useAuthStore((s) => s.clearSession);
  const navigate = useNavigate();

  const onSignOut = () => {
    // Best-effort server-side revoke; do not block on its outcome.
    if (refreshToken) {
      apiClient
        .post("/auth/logout", { refresh_token: refreshToken })
        .catch(() => {
          // Swallow — local sign-out happens regardless.
        });
    }
    clearSession();
    navigate("/login", { replace: true });
  };

  const triggerLabel = user
    ? `${user.full_name ?? user.email} (${user.role})`
    : "Account";

  return (
    <header className="flex h-14 items-center gap-3 border-b border-border bg-background px-4">
      <div className="flex-1">
        <Input
          type="search"
          placeholder="Search (coming soon)"
          aria-label="Global search"
          disabled
          className="max-w-md"
        />
      </div>
      <ThemeToggle />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" aria-label="Account menu">
            {triggerLabel}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {user ? (
            <>
              <DropdownMenuLabel>{user.email}</DropdownMenuLabel>
              <DropdownMenuLabel className="text-muted-foreground">
                Role: {user.role}
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
            </>
          ) : null}
          <DropdownMenuItem onSelect={onSignOut}>Sign out</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
