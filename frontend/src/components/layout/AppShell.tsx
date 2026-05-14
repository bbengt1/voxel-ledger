import { type ReactNode } from "react";

import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

/**
 * Protected app frame: sidebar + top bar + main content. The breadcrumbs
 * slot is rendered by individual pages via `<Breadcrumbs />` until we have
 * a real breadcrumb-driving router context.
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full min-h-screen w-full bg-background text-foreground">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  );
}
