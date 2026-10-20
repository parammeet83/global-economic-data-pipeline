import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { mockFetch } from "../test/fetchMock";
import { referenceRoutes } from "../test/referenceRoutes";
import { ComparePage } from "./ComparePage";

const comparison = {
  indicator: { indicator_code: "SP.POP.TOTL", name: "Population, total", unit: "people" },
  year: 2020,
  items: [{ country_code: "AAA", country_name: "Country A", value: 110 }],
  unavailable: [{ country_code: "BBB", country_name: "Country B" }],
};

function setup() {
  return mockFetch({ ...referenceRoutes, "/api/v1/analytics/country-comparison": { body: comparison } });
}

describe("ComparePage", () => {
  it("lists countries without a value instead of plotting zero", async () => {
    setup();
    render(
      <MemoryRouter>
        <ComparePage />
      </MemoryRouter>,
    );

    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent("No 2020 value at the source for: Country B");
    const table = screen.getByRole("table");
    expect(within(table).getByText("Country A")).toBeInTheDocument();
    expect(within(table).queryByText("Country B")).not.toBeInTheDocument();
    expect(within(table).queryByText("0 people")).not.toBeInTheDocument();
  });

  it("requires at least two countries before requesting", async () => {
    const fetchMock = setup();
    render(
      <MemoryRouter>
        <ComparePage />
      </MemoryRouter>,
    );
    await screen.findByRole("note");
    const user = userEvent.setup();

    await user.click(screen.getByLabelText("Country B"));

    expect(screen.getByRole("alert")).toHaveTextContent("Select at least 2 countries to compare.");
    const comparisonCalls = fetchMock.mock.calls.filter(([u]) => String(u).includes("country-comparison"));
    expect(comparisonCalls).toHaveLength(1);
  });
});
