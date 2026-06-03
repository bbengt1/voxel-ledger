import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useIsMobile, useMinWidth } from "@/hooks/useBreakpoint";

type Listener = () => void;

/** Install a controllable matchMedia keyed on a single "current width". */
function installMatchMedia(initialWidth: number) {
  let width = initialWidth;
  const listeners = new Set<Listener>();
  const parseMin = (q: string) => Number(/min-width:\s*(\d+)px/.exec(q)?.[1] ?? "0");

  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: (query: string) => ({
      get matches() {
        return width >= parseMin(query);
      },
      media: query,
      onchange: null,
      addEventListener: (_: string, cb: Listener) => listeners.add(cb),
      removeEventListener: (_: string, cb: Listener) => listeners.delete(cb),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });

  return {
    setWidth(next: number) {
      width = next;
      act(() => listeners.forEach((cb) => cb()));
    },
  };
}

afterEach(() => {
  // @ts-expect-error -- tear down the stub between tests
  delete window.matchMedia;
});

describe("useMinWidth", () => {
  it("reports whether the viewport meets a breakpoint and reacts to changes", () => {
    const mm = installMatchMedia(500);
    const { result } = renderHook(() => useMinWidth("lg"));
    // 500px < 1024px (lg) → false after mount.
    expect(result.current).toBe(false);

    mm.setWidth(1200);
    expect(result.current).toBe(true);

    mm.setWidth(700);
    expect(result.current).toBe(false);
  });
});

describe("useIsMobile", () => {
  it("is true below lg and false at/above it", () => {
    const mm = installMatchMedia(375);
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(true);

    mm.setWidth(1024);
    expect(result.current).toBe(false);
  });
});
