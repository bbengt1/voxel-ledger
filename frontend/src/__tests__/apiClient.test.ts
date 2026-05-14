import MockAdapter from "axios-mock-adapter";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createApiClient, setUnauthorizedHandler } from "@/api/client";
import { useAuthStore } from "@/store/useAuthStore";

describe("apiClient 401 interceptor", () => {
  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("redirects to /login?next=<original> on 401 for non-auth endpoints", async () => {
    const client = createApiClient("/api/v1");
    const mock = new MockAdapter(client);
    mock.onGet("/protected").reply(401);

    const captured: string[] = [];
    const restore = setUnauthorizedHandler(() => {
      const next = "/dashboard?tab=open";
      captured.push(`/login?next=${encodeURIComponent(next)}`);
    });

    await expect(client.get("/protected")).rejects.toThrow();

    expect(captured).toEqual([
      `/login?next=${encodeURIComponent("/dashboard?tab=open")}`,
    ]);

    restore();
  });

  it("clears the auth session on 401", async () => {
    useAuthStore.getState().setSession({
      accessToken: "at",
      refreshToken: "rt",
      user: { id: "u1", email: "x@y.z", role: "owner" },
    });

    const client = createApiClient("/api/v1");
    const mock = new MockAdapter(client);
    mock.onGet("/protected").reply(401);

    const restore = setUnauthorizedHandler(() => {});
    await expect(client.get("/protected")).rejects.toThrow();
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
    restore();
  });

  it("does NOT redirect on 401 from /auth/login", async () => {
    const client = createApiClient("/api/v1");
    const mock = new MockAdapter(client);
    mock.onPost("/auth/login").reply(401);

    const handler = vi.fn();
    const restore = setUnauthorizedHandler(handler);

    await expect(
      client.post("/auth/login", { email: "a", password: "b" }),
    ).rejects.toThrow();

    expect(handler).not.toHaveBeenCalled();
    restore();
  });

  it("attaches Authorization header when a token is set", async () => {
    useAuthStore.getState().setSession({
      accessToken: "the-token",
      refreshToken: "rt",
      user: { id: "u1", email: "x@y.z", role: "owner" },
    });

    const client = createApiClient("/api/v1");
    const mock = new MockAdapter(client);
    mock.onGet("/me").reply((config) => {
      expect(config.headers?.["Authorization"]).toBe("Bearer the-token");
      return [200, { ok: true }];
    });

    await client.get("/me");
  });
});
