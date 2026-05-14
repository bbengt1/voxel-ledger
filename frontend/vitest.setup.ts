import "@testing-library/jest-dom/vitest";

// Node 25 ships an experimental `localStorage` global that lacks the Web
// Storage interface methods, and it leaks into the jsdom environment under
// vitest. Replace it with a minimal in-memory implementation for tests so
// zustand's persist middleware and any direct localStorage access work.
function makeMemoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (key) => (map.has(key) ? (map.get(key) ?? null) : null),
    key: (index) => Array.from(map.keys())[index] ?? null,
    removeItem: (key) => {
      map.delete(key);
    },
    setItem: (key, value) => {
      map.set(key, String(value));
    },
  };
}

if (typeof window !== "undefined") {
  if (typeof window.localStorage?.setItem !== "function") {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: makeMemoryStorage(),
    });
  }
  if (typeof window.sessionStorage?.setItem !== "function") {
    Object.defineProperty(window, "sessionStorage", {
      configurable: true,
      value: makeMemoryStorage(),
    });
  }
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: window.localStorage,
  });
  Object.defineProperty(globalThis, "sessionStorage", {
    configurable: true,
    value: window.sessionStorage,
  });
}
