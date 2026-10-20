import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { POLL_INTERVAL_MS } from "../hooks/useRunPolling";
import { mockFetch } from "../test/fetchMock";
import { check, run } from "../test/fixtures";
import { RunsPage } from "./RunsPage";

const RUN_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
const history = { items: [run()], page: 1, page_size: 20, total: 1 };

function renderPage() {
  render(
    <MemoryRouter>
      <RunsPage />
    </MemoryRouter>,
  );
}

afterEach(() => vi.useRealTimers());

describe("RunsPage", () => {
  it("confirms, starts a run (202) and polls until it finishes", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let polls = 0;
    const fetchMock = mockFetch({
      "/api/v1/runs": { body: history },
      "/api/v1/pipeline/run": { status: 202, body: { run_id: RUN_ID, status: "running", status_url: `/api/v1/runs/${RUN_ID}` } },
      [`/api/v1/runs/${RUN_ID}`]: () => {
        polls += 1;
        const status = polls < 2 ? "running" : "success";
        return { body: { ...run({ run_id: RUN_ID, status, triggered_by: "api", records_loaded: 600, records_inserted: 0 }), countries_requested: 10, indicators_requested: 3, config_snapshot: null, checks: [check("numeric_value")] } };
      },
    });
    renderPage();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await screen.findByText("Run history");

    await user.click(screen.getByRole("button", { name: "Run pipeline" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("request indicator data from the public World Bank API");
    await user.click(screen.getByRole("button", { name: "Start run" }));

    expect(await screen.findByText("Running")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run in progress…" })).toBeDisabled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });

    expect(await screen.findByText(/loaded 600 · inserted 0 · value changed 0/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u, init]) => String(u).endsWith("/api/v1/pipeline/run") && init?.method === "POST")).toBe(true);
    expect(screen.getByRole("button", { name: "Run pipeline" })).toBeEnabled();
  });

  it("does nothing when the confirmation is cancelled", async () => {
    const fetchMock = mockFetch({ "/api/v1/runs": { body: history } });
    renderPage();
    await screen.findByText("Run history");
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Run pipeline" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.every(([u]) => !String(u).includes("/pipeline/run"))).toBe(true);
  });

  it("explains a conflict (409) and links to the running run", async () => {
    mockFetch({
      "/api/v1/runs": { body: history },
      "/api/v1/pipeline/run": { status: 409, body: { error: { code: "run_in_progress", message: "A pipeline run is already in progress.", run_id: RUN_ID } } },
    });
    renderPage();
    await screen.findByText("Run history");
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Run pipeline" }));
    await user.click(screen.getByRole("button", { name: "Start run" }));

    expect(await screen.findByText(/already in progress/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View the running run" })).toHaveAttribute("href", `/runs/${RUN_ID}`);
  });

  it("explains when manual runs are disabled (403)", async () => {
    mockFetch({
      "/api/v1/runs": { body: history },
      "/api/v1/pipeline/run": { status: 403, body: { error: { code: "manual_trigger_disabled", message: "Manual pipeline runs are disabled in this environment." } } },
    });
    renderPage();
    await screen.findByText("Run history");
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Run pipeline" }));
    await user.click(screen.getByRole("button", { name: "Start run" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Manual pipeline runs are disabled in this environment.");
  });
});
