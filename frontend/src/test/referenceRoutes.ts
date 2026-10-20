// Fixture responses for the reference-data endpoints used by filter pages.
import type { Country, Indicator } from "../api/types";
import { summary } from "./fixtures";

export const indicators: Indicator[] = [
  { indicator_code: "SP.POP.TOTL", name: "Population, total", description: null, unit: "people", source_name: "World Bank", frequency: "annual", observation_count: 3, first_year: 2019, last_year: 2020 },
  { indicator_code: "NY.GDP.MKTP.CD", name: "GDP (current US$)", description: null, unit: "current US$", source_name: "World Bank", frequency: "annual", observation_count: 4, first_year: 2019, last_year: 2020 },
];

export const countries: Country[] = [
  { country_code: "AAA", name: "Country A", region: null, income_level: null },
  { country_code: "BBB", name: "Country B", region: null, income_level: null },
  { country_code: "CCC", name: "Country C", region: null, income_level: null },
];

export const referenceRoutes = {
  "/api/v1/indicators": { body: indicators },
  "/api/v1/countries": { body: countries },
  "/api/v1/dashboard/summary": { body: summary() },
};
