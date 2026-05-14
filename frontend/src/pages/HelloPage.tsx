import { Button } from "@/components/ui/Button";

export function HelloPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-8">
      <section
        data-testid="hello-screen"
        className="w-full max-w-md rounded-lg border border-border bg-muted/40 p-8 shadow-sm"
      >
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">
          Voxel Ledger
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Frontend skeleton is alive. Phase 0.4 — the boring foundation.
        </p>
        <div className="mt-6">
          <Button>Hello, Tailwind</Button>
        </div>
      </section>
    </main>
  );
}
