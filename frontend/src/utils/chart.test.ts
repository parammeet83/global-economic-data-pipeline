import { describe, expect, it } from "vitest";
import { trend } from "../test/fixtures";
import { missingYears, toTrendRows } from "./chart";

describe("toTrendRows", () => {
  it("fills a missing year with null (a chart gap), not zero", () => {
    const rows = toTrendRows(trend.series);

    expect(rows).toEqual([
      { year: 2019, AAA: 100, BBB: 50 },
      { year: 2020, AAA: 110, BBB: null },
    ]);
    expect(rows[1].BBB).not.toBe(0);
    expect(missingYears(trend.series[1], rows)).toEqual([2020]);
  });

  it("handles empty series", () => {
    expect(toTrendRows([])).toEqual([]);
  });
});
