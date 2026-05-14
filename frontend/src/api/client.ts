import axios, {
  type AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from "axios";

import { useAuthStore } from "@/store/useAuthStore";

const AUTH_BYPASS_PATHS = ["/auth/login", "/auth/refresh"];

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

export function createApiClient(
  baseURL: string = import.meta.env["VITE_API_BASE_URL"] ?? "/api/v1",
): AxiosInstance {
  const client = axios.create({
    baseURL,
    headers: { "Content-Type": "application/json" },
  });

  client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = useAuthStore.getState().accessToken;
    if (token && !isAuthEndpoint(config.url)) {
      config.headers.set("Authorization", `Bearer ${token}`);
    }
    return config;
  });

  client.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => {
      const status = error.response?.status;
      const url = error.config?.url;
      if (status === 401 && !isAuthEndpoint(url)) {
        useAuthStore.getState().clearSession();
        unauthorizedHandler();
      }
      return Promise.reject(error);
    },
  );

  return client;
}

export const apiClient = createApiClient();
