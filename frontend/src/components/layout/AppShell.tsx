import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";

import { useMinWidth } from "@/hooks/useBreakpoint";

import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

/**
 * Protected app frame: skip-link + sidebar + top bar + main content.
 *
 * The skip-link is the first focusable element so keyboard users Tab past the
 * sidebar nav directly to the page content (WCAG 2.4.1).
 *
 * Responsive (epic #320): at `lg:+` the sidebar is a static left column. Below
 * `lg`, it's hidden and opens as an off-canvas drawer via the TopBar hamburger.
 * The drawer reuses Radix Dialog for a focus trap, Esc-to-close, scroll lock,
 * and an inert background; it also closes on route change and when the viewport
 * grows to desktop.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();
  const isDesktop = useMinWidth("lg");

  // Close the drawer when navigating…
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  // …and when the viewport reaches desktop (the static sidebar takes over, and
  // we must not leave a focus trap active behind it).
  useEffect(() => {
    if (isDesktop) setDrawerOpen(false);
  }, [isDesktop]);

  return (
    <div className="flex h-full min-h-screen w-full bg-background text-foreground">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:rounded focus:bg-background focus:px-3 focus:py-2 focus:text-sm focus:ring-2 focus:ring-ring focus:outline-none"
        data-testid="skip-to-content"
      >
        Skip to content
      </a>

      {/* Desktop: static sidebar. */}
      <div className="hidden lg:block">
        <Sidebar />
      </div>

      {/* Mobile: off-canvas drawer. */}
      <DialogPrimitive.Root open={drawerOpen} onOpenChange={setDrawerOpen}>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/50 lg:hidden" />
          <DialogPrimitive.Content
            className="fixed inset-y-0 left-0 z-50 focus:outline-none lg:hidden"
            data-testid="nav-drawer"
            aria-label="Navigation"
            aria-describedby={undefined}
          >
            <DialogPrimitive.Title className="sr-only">Navigation</DialogPrimitive.Title>
            <Sidebar />
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onMenuClick={() => setDrawerOpen(true)} />
        <main
          id="main-content"
          tabIndex={-1}
          className="flex-1 overflow-auto p-4 focus:outline-none sm:p-6"
        >
          {children}
        </main>
      </div>
    </div>
  );
}
