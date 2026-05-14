import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ThemeProvider,
  useTheme,
  type ThemePreference,
} from "@/components/theme/ThemeProvider";

const STORAGE_KEY = "voxel-ledger:theme";

function setSystemPreference(dark: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: (query: string) => {
      const matches = query.includes("dark") && dark;
      return {
        matches,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      };
    },
  });
}

function Probe() {
  const { theme, effectiveTheme, setTheme } = useTheme();
  return (
    <div>
      <span data-testid="pref">{theme}</span>
      <span data-testid="effective">{effectiveTheme}</span>
      {(["light", "dark", "system"] as const).map((t: ThemePreference) => (
        <button
          key={t}
          type="button"
          onClick={() => setTheme(t)}
          data-testid={`set-${t}`}
        >
          {t}
        </button>
      ))}
    </div>
  );
}

describe("<ThemeProvider />", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.classList.remove("dark");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("defaults to system and uses prefers-color-scheme: dark when set", () => {
    setSystemPreference(true);
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("pref")).toHaveTextContent("system");
    expect(screen.getByTestId("effective")).toHaveTextContent("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("uses light when system preference is light", () => {
    setSystemPreference(false);
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("effective")).toHaveTextContent("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("persists the explicit choice to localStorage", async () => {
    setSystemPreference(false);
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    await user.click(screen.getByTestId("set-dark"));

    expect(screen.getByTestId("pref")).toHaveTextContent("dark");
    expect(screen.getByTestId("effective")).toHaveTextContent("dark");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("reads stored preference on mount", () => {
    localStorage.setItem(STORAGE_KEY, "dark");
    setSystemPreference(false);
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("pref")).toHaveTextContent("dark");
    expect(screen.getByTestId("effective")).toHaveTextContent("dark");
  });

  it("switches back to system after explicit choice", async () => {
    setSystemPreference(true);
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    await user.click(screen.getByTestId("set-light"));
    expect(screen.getByTestId("effective")).toHaveTextContent("light");

    await act(async () => {
      await user.click(screen.getByTestId("set-system"));
    });
    expect(screen.getByTestId("pref")).toHaveTextContent("system");
    expect(screen.getByTestId("effective")).toHaveTextContent("dark");
  });
});
