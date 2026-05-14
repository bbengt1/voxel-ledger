/**
 * Typed thin wrapper around the shared axios instance.
 *
 * The generated `types.ts` (from `openapi-typescript`) is the contract: it
 * exports a `paths` interface keyed by URL, with request/response shapes
 * derived from the FastAPI spec. This file is the *adapter* — it lets you
 * call `api.get("/api/v1/auth/me")` and get a response typed against the
 * spec, without hand-maintaining a single shape.
 *
 * Kept deliberately tiny: it composes with the existing axios client
 * (interceptors, auth header injection, 401 redirect) instead of replacing
 * it. If you need an escape hatch, import `apiClient` directly and accept
 * that you're outside the type-safe path.
 *
 * Coverage notes:
 *  - JSON request/response bodies only.
 *  - `Form` bodies and multipart uploads are not modeled here yet; reach
 *    for `apiClient` directly until we have a real endpoint that needs it.
 *  - Path parameter interpolation is the caller's responsibility today
 *    (use template literals). Once we have parameterized routes we'll add
 *    a small helper.
 */

import type { AxiosRequestConfig, AxiosResponse } from "axios";

import { apiClient } from "./client";
import type { paths } from "./types";

type HttpMethod = "get" | "post" | "put" | "delete" | "patch";

/** Paths that define the given HTTP method in the generated spec. */
type PathsWith<M extends HttpMethod> = {
  [P in keyof paths]: paths[P] extends { [K in M]: unknown } ? P : never;
}[keyof paths];

type Operation<P extends keyof paths, M extends HttpMethod> = paths[P] extends {
  [K in M]: infer Op;
}
  ? Op
  : never;

type ResponseBody<P extends keyof paths, M extends HttpMethod> = Operation<
  P,
  M
> extends {
  responses: {
    200: { content: { "application/json": infer R } };
  };
}
  ? R
  : Operation<P, M> extends {
        responses: {
          201: { content: { "application/json": infer R } };
        };
      }
    ? R
    : unknown;

type RequestBody<P extends keyof paths, M extends HttpMethod> = Operation<
  P,
  M
> extends {
  requestBody: { content: { "application/json": infer B } };
}
  ? B
  : Operation<P, M> extends {
        requestBody?: { content: { "application/json": infer B } };
      }
    ? B | undefined
    : undefined;

export async function get<P extends PathsWith<"get">>(
  url: P,
  config?: AxiosRequestConfig,
): Promise<AxiosResponse<ResponseBody<P, "get">>> {
  return apiClient.get<ResponseBody<P, "get">>(url as string, config);
}

export async function post<P extends PathsWith<"post">>(
  url: P,
  body?: RequestBody<P, "post">,
  config?: AxiosRequestConfig,
): Promise<AxiosResponse<ResponseBody<P, "post">>> {
  return apiClient.post<ResponseBody<P, "post">>(url as string, body, config);
}

export async function put<P extends PathsWith<"put">>(
  url: P,
  body?: RequestBody<P, "put">,
  config?: AxiosRequestConfig,
): Promise<AxiosResponse<ResponseBody<P, "put">>> {
  return apiClient.put<ResponseBody<P, "put">>(url as string, body, config);
}

export async function patch<P extends PathsWith<"patch">>(
  url: P,
  body?: RequestBody<P, "patch">,
  config?: AxiosRequestConfig,
): Promise<AxiosResponse<ResponseBody<P, "patch">>> {
  return apiClient.patch<ResponseBody<P, "patch">>(url as string, body, config);
}

export async function del<P extends PathsWith<"delete">>(
  url: P,
  config?: AxiosRequestConfig,
): Promise<AxiosResponse<ResponseBody<P, "delete">>> {
  return apiClient.delete<ResponseBody<P, "delete">>(url as string, config);
}

/** Convenience bundle, so callers can `import { api } from "@/api/typed"`. */
export const api = { get, post, put, patch, del };

// Re-export the axios instance so consumers have a single import surface
// without losing the underlying client when they need it.
export { apiClient } from "./client";
export type { paths, components, operations } from "./types";
