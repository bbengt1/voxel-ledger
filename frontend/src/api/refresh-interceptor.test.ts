import MockAdapter from "axios-mock-adapter";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createApiClient, setUnauthorizedHandler } from "@/api/client";
import { useAuthStore } from "@/store/useAuthStore";

function seedSession(accessToken = "old-at", refreshToken = "rt-1") {
  useAuthStore.getState().setSession({
    accessToken,
    refreshToken,
    user: { id: "u1", email: "x@y.z", role: "owner" },
  });
}

describe("apiClient refresh interceptor", () => {
  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("refreshes on 401, retries the original request, returns the response", async () => {
    seedSession();
    const client = createApiClient("");
    const mock = new MockAdapter(client);

    let protectedCalls = 0;
    mock.onGet("/protected").reply((config) => {
      protectedCalls += 1;
      if (protectedCalls === 1) {
        return [401];
      }
      // Second call: must carry the NEW token.
      expect(config.headers?.["Authorization"]).toBe("Bearer new-at");
      return [200, { ok: true }];
    });

    mock.onPost("/api/v1/auth/refresh").reply(200, {
      access_token: "new-at",
      refresh_token: "new-rt",
      expires_in: 900,
      token_type: "bearer",
    });

    const response = await client.get("/protected");

    expect(response.status).toBe(200);
    expect(response.data).toEqual({ ok: true });
    expect(protectedCalls).toBe(2);
    expect(useAuthStore.getState().accessToken).toBe("new-at");
    expect(useAuthStore.getState().refreshToken).toBe("new-rt");
  });

  it("only fires one refresh request under a burst of concurrent 401s", async () => {
    seedSession();
    const client = createApiClient("");
    const mock = new MockAdapter(client);

    const seen: Record<string, number> = {};
    function bumpCall(path: string) {
      seen[path] = (seen[path] ?? 0) + 1;
      return seen[path]!;
    }

    mock.onGet("/a").reply(() => {
      const n = bumpCall("a");
      return n === 1 ? [401] : [200, { which: "a" }];
    });
    mock.onGet("/b").reply(() => {
      const n = bumpCall("b");
      return n === 1 ? [401] : [200, { which: "b" }];
    });
    mock.onGet("/c").reply(() => {
      const n = bumpCall("c");
      return n === 1 ? [401] : [200, { which: "c" }];
    });

    let refreshCalls = 0;
    mock.onPost("/api/v1/auth/refresh").reply(() => {
      refreshCalls += 1;
      return [
        200,
        {
          access_token: "new-at",
          refresh_token: "new-rt",
          expires_in: 900,
          token_type: "bearer",
        },
      ];
    });

    const [a, b, c] = await Promise.all([
      client.get("/a"),
      client.get("/b"),
      client.get("/c"),
    ]);

    expect(a.data).toEqual({ which: "a" });
    expect(b.data).toEqual({ which: "b" });
    expect(c.data).toEqual({ which: "c" });
    expect(refreshCalls).toBe(1);
  });

  it("redirects to /login and clears the session when refresh fails", async () => {
    seedSession();
    const client = createApiClient("");
    const mock = new MockAdapter(client);

    mock.onGet("/protected").reply(401);
    mock.onPost("/api/v1/auth/refresh").reply(401);

    const handler = vi.fn();
    const restore = setUnauthorizedHandler(handler);

    await expect(client.get("/protected")).rejects.toThrow();

    expect(handler).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState().accessToken).toBeNull();
    restore();
  });

  it("does not attempt refresh when there is no refresh token", async () => {
    // Empty store: no refresh token, no user.
    const client = createApiClient("");
    const mock = new MockAdapter(client);

    mock.onGet("/protected").reply(401);
    const refreshSpy = vi.fn(() => [401, {}] as [number, object]);
    mock.onPost("/api/v1/auth/refresh").reply(refreshSpy);

    const handler = vi.fn();
    const restore = setUnauthorizedHandler(handler);

    await expect(client.get("/protected")).rejects.toThrow();

    expect(refreshSpy).not.toHaveBeenCalled();
    expect(handler).toHaveBeenCalledTimes(1);
    restore();
  });
});
