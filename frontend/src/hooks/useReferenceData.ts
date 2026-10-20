import { apiGet } from "../api/client";
import type { Country, DashboardSummary, Indicator } from "../api/types";
import { useApi } from "./useApi";

/** Indicators, countries and configured defaults, needed by the filter-driven pages. */
export function useReferenceData() {
  const indicators = useApi((s) => apiGet<Indicator[]>("/api/v1/indicators", {}, s), "indicators");
  const countries = useApi((s) => apiGet<Country[]>("/api/v1/countries", {}, s), "countries");
  const summary = useApi((s) => apiGet<DashboardSummary>("/api/v1/dashboard/summary", {}, s), "summary");
  const error = indicators.error ?? countries.error ?? summary.error;
  const loading = indicators.loading || countries.loading || summary.loading;
  const reload = () => {
    indicators.reload();
    countries.reload();
    summary.reload();
  };
  return {
    indicators: indicators.data,
    countries: countries.data,
    defaults: summary.data?.defaults ?? null,
    loading,
    error,
    reload,
  };
}
