import { type ReactNode } from "react";

import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

/**
 * Protected app frame: skip-link + sidebar + top bar + main content.
 * The skip-link is the first focusable element so keyboard users
 * Tab past the sidebar nav directly to the page content (WCAG
 * 2.4.1).
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full min-h-screen w-full bg-background text-foreground">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-background focus:px-3 focus:py-2 focus:text-sm focus:ring-2 focus:ring-ring focus:outline-none"
        data-testid="skip-to-content"
      >
        Skip to content
      </a>
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main
          id="main-content"
          tabIndex={-1}
          className="flex-1 overflow-auto p-6 focus:outline-none"
        >
          {children}
        </main>
      </div>
    </div>
  );
}
