import { describe, expect, it } from "vitest";
import { buildUrl } from "../api/client";
import { MISSING, formatAxis, formatCount, formatDuration, formatValue } from "./format";
import { qualityVerdict } from "./quality";
import { check, run } from "../test/fixtures";

describe("formatValue", () => {
  it("renders missing values as an em dash, never as zero", () => {
    expect(formatValue(null, "people")).toBe(MISSING);
    expect(formatValue(undefined, "current US$")).toBe(MISSING);
    expect(formatValue(Number.NaN, "% of total labor force")).toBe(MISSING);
    expect(formatCount(null)).toBe(MISSING);
  });

  it("keeps a real zero as zero", () => {
    expect(formatValue(0, "people")).toBe("0 people");
    expect(formatCount(0)).toBe("0");
  });

  it("formats units", () => {
    expect(formatValue(2.675e12, "current US$")).toBe("US$2.68T");
    expect(formatValue(1450935791, "people")).toBe("1.45B people");
    expect(formatValue(4.172, "% of total labor force")).toBe("4.17%");
    expect(formatValue(1234567.891, "current US$", "full")).toBe("US$1,234,567.89");
    expect(formatAxis(3e13, "current US$")).toBe("US$30T");
  });

  it("formats durations", () => {
    expect(formatDuration(3.77)).toBe("3.8 s");
    expect(formatDuration(125)).toBe("2 min 5 s");
    expect(formatDuration(null)).toBe(MISSING);
  });
});

describe("buildUrl", () => {
  it("repeats array parameters and drops empty values", () => {
    expect(buildUrl("/api/v1/analytics/trend", { indicator_code: "SP.POP.TOTL", country_code: ["IND", "USA"], start_year: "" })).toBe(
      "/api/v1/analytics/trend?indicator_code=SP.POP.TOTL&country_code=IND&country_code=USA",
    );
  });
});

describe("qualityVerdict", () => {
  it("is never passed for a failed run or a failed check", () => {
    expect(qualityVerdict(run({ status: "failed" }), [check("numeric_value")]).status).toBe("failed");
    expect(qualityVerdict(run(), [check("numeric_value", "failed")]).status).toBe("failed");
    expect(qualityVerdict(run(), [check("null_value_rate", "warning")]).status).toBe("warning");
    expect(qualityVerdict(run({ status: "partial_success" }), [check("numeric_value")]).status).toBe("warning");
    expect(qualityVerdict(run(), [check("numeric_value")]).status).toBe("passed");
    expect(qualityVerdict(null, []).status).toBe("none");
  });
});
