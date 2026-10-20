import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { mockFetch, requestedUrls } from "../test/fetchMock";
import { check, quality, run, summary, trend } from "../test/fixtures";
import { OverviewPage } from "./OverviewPage";

function renderPage() {
  return render(
    <MemoryRouter>
      <OverviewPage />
    </MemoryRouter>,
  );
}

const runsPage = { items: [run()], page: 1, page_size: 5, total: 1 };

describe("OverviewPage", () => {
  it("shows a loading state first, then real KPIs from the API", async () => {
    const fetchMock = mockFetch({
      "/api/v1/dashboard/summary": { body: summary() },
      "/api/v1/quality/latest": { body: quality },
      "/api/v1/runs": { body: runsPage },
      "/api/v1/analytics/trend": { body: trend },
    });

    renderPage();
    expect(screen.getByRole("status")).toHaveTextContent("Loading dashboard");

    expect(await screen.findByText("Observations")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(await screen.findByText("All checks passed")).toBeInTheDocument();
    const trendCall = requestedUrls(fetchMock).find((u) => u.pathname === "/api/v1/analytics/trend")!;
    expect(trendCall.searchParams.get("indicator_code")).toBe("SP.POP.TOTL");
    expect(trendCall.searchParams.getAll("country_code")).toEqual(["AAA", "BBB"]); // defaults come from the backend
  });

  it("shows setup guidance when the database has no observations", async () => {
    mockFetch({
      "/api/v1/dashboard/summary": { body: summary({ observations: 0, countries: 0, indicators: 0, latest_run: null, latest_successful_load_at: null }) },
      "/api/v1/quality/latest": { body: { run: null, checks: [] } },
      "/api/v1/runs": { body: { items: [], page: 1, page_size: 5, total: 0 } },
    });

    renderPage();

    expect(await screen.findByText("No observations loaded yet")).toBeInTheDocument();
    expect(screen.getByText(/python -m src.pipeline.cli run/)).toBeInTheDocument();
  });

  it("explains when the backend cannot be reached", async () => {
    mockFetch({ "*": "network-error" });

    renderPage();

    expect(await screen.findByText("Cannot reach the backend")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("explains a database outage without raw details", async () => {
    mockFetch({ "*": { status: 503, body: { error: { code: "database_unavailable", message: "The database is unavailable. Try again later." } } } });

    renderPage();

    expect(await screen.findByText("Database unavailable")).toBeInTheDocument();
    expect(screen.getByText("The database is unavailable. Try again later.")).toBeInTheDocument();
  });

  it("warns about a failed latest run and never shows an all-clear for it", async () => {
    const failed = run({ status: "failed", error_summary: "2 of 2 series failed" });
    mockFetch({
      "/api/v1/dashboard/summary": { body: summary({ latest_run: failed }) },
      "/api/v1/quality/latest": { body: { run: failed, checks: [check("extraction_requests_succeeded", "failed")] } },
      "/api/v1/runs": { body: { ...runsPage, items: [failed] } },
      "/api/v1/analytics/trend": { body: trend },
    });

    renderPage();

    expect(await screen.findByText(/most recent pipeline run failed/)).toBeInTheDocument();
    expect(await screen.findByText("Latest run failed")).toBeInTheDocument();
    expect(screen.queryByText("All checks passed")).not.toBeInTheDocument();
  });
});
