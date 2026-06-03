import { useEffect, useState } from "react";

/**
 * Tailwind's default breakpoint min-widths (px). Mobile-first: a value being
 * "active" means the viewport is at least that wide.
 */
export const BREAKPOINTS = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  "2xl": 1536,
} as const;

export type Breakpoint = keyof typeof BREAKPOINTS;

/**
 * SSR-safe `matchMedia` subscription. Returns `true` when the viewport is at
 * least `min-width: <breakpoint>`. Defaults to `false` before mount so the
 * first paint assumes mobile (matching our mobile-first defaults) and widens
 * once measured — never the other way around, which would flash desktop
 * chrome on a phone.
 *
 * Prefer pure CSS (`hidden lg:block`) for layout that can be expressed with
 * Tailwind variants; reach for this hook only when behavior (not just styling)
 * must branch on width — e.g. a drawer that traps focus on mobile but not on
 * desktop.
 */
export function useMinWidth(breakpoint: Breakpoint): boolean {
  const query = `(min-width: ${BREAKPOINTS[breakpoint]}px)`;
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** `true` below the `lg` breakpoint (the desktop sidebar threshold). */
export function useIsMobile(): boolean {
  return !useMinWidth("lg");
}
