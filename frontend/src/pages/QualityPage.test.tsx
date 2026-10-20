import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { mockFetch } from "../test/fetchMock";
import { check, run } from "../test/fixtures";
import { QualityPage } from "./QualityPage";

function renderPage() {
  render(
    <MemoryRouter>
      <QualityPage />
    </MemoryRouter>,
  );
}

describe("QualityPage", () => {
  it("never shows an all-clear when the latest run failed", async () => {
    mockFetch({
      "/api/v1/quality/latest": {
        body: { run: run({ status: "failed", error_summary: "2 of 2 series failed" }), checks: [check("extraction_requests_succeeded", "failed")] },
      },
    });
    renderPage();

    expect(await screen.findByText("Latest run failed")).toBeInTheDocument();
    expect(screen.queryByText("All checks passed")).not.toBeInTheDocument();
    expect(screen.getByText("2 of 2 series failed")).toBeInTheDocument();
  });

  it("explains null values as missing source observations", async () => {
    mockFetch({ "/api/v1/quality/latest": { body: { run: run(), checks: [check("null_value_rate", "warning")] } } });
    renderPage();

    expect(await screen.findByText("Passed with warnings")).toBeInTheDocument();
    expect(screen.getByText(/missing source observations/)).toBeInTheDocument();
    expect(screen.getByText(/never stored or shown as zero/)).toBeInTheDocument();
  });

  it("shows an empty state before any run has finished", async () => {
    mockFetch({ "/api/v1/quality/latest": { body: { run: null, checks: [] } } });
    renderPage();

    expect(await screen.findByText("No finished pipeline run yet")).toBeInTheDocument();
  });
});
