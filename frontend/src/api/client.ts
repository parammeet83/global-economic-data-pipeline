// Typed client for the FastAPI backend. The browser never talks to the database.

export type QueryValue = string | number | undefined | null | (string | number)[];

/** A failed request. `kind` separates "backend unreachable" from HTTP errors from the API. */
export class ApiError extends Error {
  readonly kind: "network" | "http";
  readonly status: number;
  readonly code: string;
  readonly body: Record<string, unknown> | null;

  constructor(kind: "network" | "http", status: number, code: string, message: string, body: Record<string, unknown> | null = null) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.code = code;
    this.body = body;
  }

  get isDatabaseUnavailable(): boolean {
    return this.status === 503;
  }
}

export function buildUrl(path: string, params: Record<string, QueryValue> = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    for (const item of Array.isArray(value) ? value : [value]) search.append(key, String(item));
  }
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

async function request<T>(method: "GET" | "POST", path: string, params?: Record<string, QueryValue>, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path, params), { method, signal, headers: { Accept: "application/json" } });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("network", 0, "network_error", "Cannot reach the backend API. Is the FastAPI server running?");
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const error = (body as { error?: { code?: string; message?: string } } | null)?.error;
    const message = error?.message ?? (response.status === 503 ? "The database is unavailable." : `Request failed (HTTP ${response.status}).`);
    throw new ApiError("http", response.status, error?.code ?? "http_error", message, (error as Record<string, unknown>) ?? null);
  }
  return body as T;
}

export const apiGet = <T>(path: string, params?: Record<string, QueryValue>, signal?: AbortSignal) =>
  request<T>("GET", path, params, signal);

export const apiPost = <T>(path: string) => request<T>("POST", path);
