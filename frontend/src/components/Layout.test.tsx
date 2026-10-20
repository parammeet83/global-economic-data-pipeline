import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiGet, apiPost } from "../api/client";
import { getLastRefresh } from "../api/refresh";
import { mockFetch } from "../test/fetchMock";
import { Layout } from "./Layout";

const healthy = { "/health": { body: { status: "ok", database: "ok" } } };

function renderLayout() {
  render(
    <MemoryRouter>
      <Layout title="Overview">
        <p>content</p>
      </Layout>
    </MemoryRouter>,
  );
}

afterEach(() => vi.useRealTimers());

describe("last refresh indicator", () => {
  it("shows a clear initial state and is not set by the health check", async () => {
    mockFetch(healthy);
    renderLayout();

    expect(await screen.findByText(/API online/)).toBeInTheDocument();
    expect(screen.getByText("Not refreshed yet")).toBeInTheDocument();
    expect(getLastRefresh()).toBeNull();
  });

  it("shows the time of the latest successful data response", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(2026, 9, 20, 10, 15, 30));
    mockFetch({ ...healthy, "/api/v1/countries": { body: [] } });
    renderLayout();

    await act(async () => {
      await apiGet("/api/v1/countries");
    });

    expect(screen.getByText(/Last refresh/)).toHaveTextContent("Last refresh 10:15:30");
    expect(screen.queryByText("Not refreshed yet")).not.toBeInTheDocument();

    vi.setSystemTime(new Date(2026, 9, 20, 10, 16, 5));
    await act(async () => {
      await apiGet("/api/v1/countries");
    });
    expect(screen.getByText(/Last refresh/)).toHaveTextContent("Last refresh 10:16:05");
  });

  it("is not updated by failed requests, network errors or POSTs", async () => {
    mockFetch({
      ...healthy,
      "/api/v1/runs": { status: 503, body: { error: { code: "database_unavailable", message: "The database is unavailable." } } },
      "/api/v1/pipeline/run": { status: 202, body: { run_id: "x", status: "running", status_url: "/api/v1/runs/x" } },
      "/api/v1/countries": "network-error",
    });
    renderLayout();

    await act(async () => {
      await apiGet("/api/v1/runs").catch(() => undefined);
      await apiGet("/api/v1/countries").catch(() => undefined);
      await apiPost("/api/v1/pipeline/run");
    });

    expect(getLastRefresh()).toBeNull();
    expect(screen.getByText("Not refreshed yet")).toBeInTheDocument();
  });
});
