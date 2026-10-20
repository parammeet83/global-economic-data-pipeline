import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { mockFetch, requestedUrls } from "../test/fetchMock";
import { trend } from "../test/fixtures";
import { referenceRoutes } from "../test/referenceRoutes";
import { ExplorePage, validateFilters } from "./ExplorePage";

const observations = {
  items: [
    { country_code: "AAA", country_name: "Country A", indicator_code: "SP.POP.TOTL", indicator_name: "Population, total", year: 2020, value: 110, unit: "people", ingested_at: "2026-10-20T07:26:41Z" },
  ],
  page: 1,
  page_size: 25,
  total: 1,
};

function setup() {
  const fetchMock = mockFetch({
    ...referenceRoutes,
    "/api/v1/analytics/trend": { body: trend },
    "/api/v1/observations": { body: observations },
  });
  render(
    <MemoryRouter>
      <ExplorePage />
    </MemoryRouter>,
  );
  return fetchMock;
}

describe("validateFilters", () => {
  const ok = { indicator: "SP.POP.TOTL", countries: ["AAA"], startYear: "2019", endYear: "2020" };
  it("accepts valid filters and rejects invalid ones", () => {
    expect(validateFilters(ok)).toBeNull();
    expect(validateFilters({ ...ok, startYear: "2021" })).toMatch(/Start year must be less than or equal/);
    expect(validateFilters({ ...ok, startYear: "1800" })).toMatch(/between 1900 and 2200/);
    expect(validateFilters({ ...ok, countries: [] })).toMatch(/at least one country/);
    expect(validateFilters({ ...ok, countries: Array.from({ length: 11 }, (_, i) => `C${i}`) })).toMatch(/at most 10/);
  });
});

describe("ExplorePage", () => {
  it("loads defaults from the backend and sends them as filters", async () => {
    const fetchMock = setup();

    expect(await screen.findByText("Population, total", { selector: "td" })).toBeInTheDocument();
    const call = requestedUrls(fetchMock).find((u) => u.pathname === "/api/v1/observations")!;
    expect(call.searchParams.get("indicator_code")).toBe("SP.POP.TOTL");
    expect(call.searchParams.getAll("country_code")).toEqual(["AAA", "BBB"]);
    expect(call.searchParams.get("start_year")).toBe("2019");
    expect(call.searchParams.get("end_year")).toBe("2020");
    expect(screen.getByText("110 people")).toBeInTheDocument();
    // the gap for Country B in 2020 is described, not drawn as zero
    expect(screen.getByText(/Gaps mark years with no source value: Country B \(2020\)/)).toBeInTheDocument();
  });

  it("shows an inline error and does not send an invalid year range", async () => {
    const fetchMock = setup();
    await screen.findByText("Population, total", { selector: "td" });
    const before = fetchMock.mock.calls.length;

    const user = userEvent.setup();
    const start = screen.getByLabelText("Start year");
    await user.clear(start);
    await user.type(start, "2025");
    await user.click(screen.getByRole("button", { name: "Apply filters" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Start year must be less than or equal to end year.");
    expect(fetchMock.mock.calls.length).toBe(before);
  });

  it("re-fetches with the new selection after Apply", async () => {
    const fetchMock = setup();
    await screen.findByText("Population, total", { selector: "td" });

    const user = userEvent.setup();
    await user.click(screen.getByLabelText("Country C"));
    await user.click(screen.getByRole("button", { name: "Apply filters" }));

    const last = requestedUrls(fetchMock).filter((u) => u.pathname === "/api/v1/analytics/trend").at(-1)!;
    expect(last.searchParams.getAll("country_code")).toEqual(["AAA", "BBB", "CCC"]);
  });
});
