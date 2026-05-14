import { useAuthStore } from "@/store/useAuthStore";

export function HomePage() {
  const user = useAuthStore((s) => s.user);

  return (
    <section
      data-testid="home-screen"
      className="rounded-lg border border-border bg-muted/30 p-6"
    >
      <h1 className="text-2xl font-semibold tracking-tight">Welcome</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        {user
          ? `Logged in as ${user.email} (${user.role}).`
          : "Logged in."}
      </p>
      <p className="mt-4 text-xs text-muted-foreground">
        Bounded-context pages land in their respective phases.
      </p>
    </section>
  );
}
