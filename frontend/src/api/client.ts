import axios, {
  type AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from "axios";

import { useAuthStore } from "@/store/useAuthStore";

const AUTH_BYPASS_PATHS = ["/api/v1/auth/login", "/api/v1/auth/refresh"];

/**
 * Default redirect-on-401 handler. Captures the current URL and sends the
 * browser to `/login?next=<encoded>`. Replaceable for testing via
 * {@link setUnauthorizedHandler}.
 */
let unauthorizedHandler: () => void = () => {
  if (typeof window === "undefined") return;
  const next = window.location.pathname + window.location.search;
  window.location.assign(`/login?next=${encodeURIComponent(next)}`);
};

export function setUnauthorizedHandler(handler: () => void): () => void {
  const previous = unauthorizedHandler;
  unauthorizedHandler = handler;
  return () => {
    unauthorizedHandler = previous;
  };
}

function isAuthEndpoint(url: string | undefined): boolean {
  if (!url) return false;
  return AUTH_BYPASS_PATHS.some((path) => url.includes(path));
}

/**
 * Shape of a successful `/auth/refresh` response. Mirrors `TokenPair` in the
 * generated types but kept local to avoid a circular import via `typed.ts`.
 */
interface TokenPairResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: string;
}

interface RetryableConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

export function createApiClient(
  // baseURL is the *origin* only — every call site provides the full path
  // starting with `/api/v1/...`, matching the generated OpenAPI types in
  // `types.ts`. Mixing a versioned baseURL with versioned spec paths produced
  // doubled-up URLs (`/api/v1/api/v1/users`) and was the source of a real
  // production-shaped 404 on the admin pages.
  baseURL: string = import.meta.env["VITE_API_BASE_URL"] ?? "",
): AxiosInstance {
  const client = axios.create({
    baseURL,
    headers: { "Content-Type": "application/json" },
  });

  // Single in-flight refresh promise. A burst of concurrent 401s should
  // produce exactly one /auth/refresh request; everyone else awaits it.
  let pendingRefresh: Promise<string | null> | null = null;

  async function refreshAccessToken(): Promise<string | null> {
    const refreshToken = useAuthStore.getState().refreshToken;
    if (!refreshToken) return null;
    try {
      const response = await client.post<TokenPairResponse>(
        "/api/v1/auth/refresh",
        { refresh_token: refreshToken },
      );
      const data = response.data;
      const user = useAuthStore.getState().user;
      if (!user) return null;
      useAuthStore.getState().setSession({
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
        user,
      });
      return data.access_token;
    } catch {
      return null;
    }
  }

  client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = useAuthStore.getState().accessToken;
    if (token && !isAuthEndpoint(config.url)) {
      config.headers.set("Authorization", `Bearer ${token}`);
    }
    return config;
  });

  client.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const status = error.response?.status;
      const original = error.config as RetryableConfig | undefined;
      const url = original?.url;

      if (status !== 401 || isAuthEndpoint(url) || !original) {
        return Promise.reject(error);
      }

      if (original._retry) {
        // Already retried once — give up.
        useAuthStore.getState().clearSession();
        unauthorizedHandler();
        return Promise.reject(error);
      }

      // Reuse the in-flight refresh if one is already running.
      if (!pendingRefresh) {
        pendingRefresh = refreshAccessToken().finally(() => {
          pendingRefresh = null;
        });
      }
      const newToken = await pendingRefresh;

      if (!newToken) {
        useAuthStore.getState().clearSession();
        unauthorizedHandler();
        return Promise.reject(error);
      }

      original._retry = true;
      const retryConfig: AxiosRequestConfig = { ...original };
      // Ensure the retry uses the freshly minted access token.
      retryConfig.headers = {
        ...(retryConfig.headers as Record<string, string>),
        Authorization: `Bearer ${newToken}`,
      };
      return client.request(retryConfig);
    },
  );

  return client;
}

export const apiClient = createApiClient();
