import { vi } from "vitest";

type Route = { status?: number; body: unknown } | ((url: URL) => { status?: number; body: unknown });

/**
 * Replaces global fetch. Keys are pathnames (e.g. "/api/v1/runs"); a key of "*" matches anything.
 * Returns the mock so tests can inspect requested URLs. Data here is fixture data only.
 */
export function mockFetch(routes: Record<string, Route | "network-error">) {
  const mock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input.toString(), "http://localhost");
    const route = routes[url.pathname] ?? routes["*"];
    if (route === undefined) throw new Error(`Unmocked request: ${url.pathname}`);
    if (route === "network-error") throw new TypeError("Failed to fetch");
    const { status = 200, body } = typeof route === "function" ? route(url) : route;
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

export function requestedUrls(mock: ReturnType<typeof mockFetch>): URL[] {
  return mock.mock.calls.map(([input]) => new URL(String(input), "http://localhost"));
}
