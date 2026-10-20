import type { QualityCheck } from "../api/types";
import { formatCount, humanize } from "../utils/format";
import { StatusBadge } from "./StatusBadge";

export const CHECK_DESCRIPTIONS: Record<string, string> = {
  extraction_requests_succeeded: "Every indicator series was fetched after bounded retries.",
  api_page_count_consistent: "Rows received match the API's reported total and page count.",
  required_fields_present: "Rows have a country code, indicator code and year.",
  valid_country_code: "Country codes are configured ISO-3 codes (aggregates excluded).",
  valid_indicator_code: "Indicator codes are configured.",
  year_in_range: "Years are integers inside the configured window.",
  numeric_value: "Non-null values are finite numbers that fit NUMERIC(24,6).",
  null_value_rate: "Source gaps (null values). Counted and skipped, never stored as zero.",
  unique_business_key: "One row per country, indicator and year before loading.",
};

export function ChecksTable({ checks }: { checks: QualityCheck[] }) {
  return (
    <div className="table-wrap">
      <table>
        <caption className="sr-only">Data-quality check results</caption>
        <thead>
          <tr>
            <th scope="col">Check</th>
            <th scope="col">Status</th>
            <th scope="col" className="num">Checked</th>
            <th scope="col" className="num">Failed</th>
            <th scope="col">Details</th>
          </tr>
        </thead>
        <tbody>
          {checks.map((c) => (
            <tr key={c.check_name}>
              <td>
                <strong>{humanize(c.check_name)}</strong>
                <div className="muted">{CHECK_DESCRIPTIONS[c.check_name] ?? c.check_name}</div>
              </td>
              <td><StatusBadge status={c.status} /></td>
              <td className="num">{formatCount(c.records_checked)}</td>
              <td className="num">{formatCount(c.records_failed)}</td>
              <td>
                {c.details && Object.keys(c.details).length > 0 ? (
                  <details>
                    <summary>Show</summary>
                    <pre>{JSON.stringify(c.details, null, 2)}</pre>
                  </details>
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
