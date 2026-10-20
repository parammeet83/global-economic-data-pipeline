import { apiGet } from "../api/client";
import type { Indicator } from "../api/types";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { useApi } from "../hooks/useApi";
import { MISSING, formatCount } from "../utils/format";

export function AboutPage() {
  const indicators = useApi((s) => apiGet<Indicator[]>("/api/v1/indicators", {}, s), "indicators");

  return (
    <div className="stack">
      <section className="card stack-sm">
        <h2>Data source</h2>
        <p>
          Observations come from the{" "}
          <a href="https://datahelpdesk.worldbank.org/knowledgebase/topics/125589-developer-information" target="_blank" rel="noreferrer">
            World Bank Indicators API
          </a>{" "}
          (<code>https://api.worldbank.org/v2</code>). The pipeline requests a fixed, configurable set of countries (ISO-3 codes), indicators and
          years, validates every row and loads it idempotently into PostgreSQL.
        </p>
        <p>
          Review the{" "}
          <a href="https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets" target="_blank" rel="noreferrer">
            World Bank terms of use for datasets
          </a>{" "}
          for licensing and attribution before reusing the data.
        </p>
      </section>

      <section className="card">
        <h2>Indicators</h2>
        {indicators.loading && <Loading />}
        {indicators.error && <ErrorState error={indicators.error} onRetry={indicators.reload} />}
        {indicators.data && indicators.data.length === 0 && <EmptyState title="No indicators loaded yet">Run the pipeline once.</EmptyState>}
        {indicators.data && indicators.data.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Indicator</th>
                  <th scope="col">Code</th>
                  <th scope="col">Unit</th>
                  <th scope="col">Coverage loaded</th>
                </tr>
              </thead>
              <tbody>
                {indicators.data.map((i) => (
                  <tr key={i.indicator_code}>
                    <td>
                      <strong>{i.name}</strong>
                      {i.description && <div className="muted">{i.description}</div>}
                    </td>
                    <td><code>{i.indicator_code}</code></td>
                    <td>{i.unit}</td>
                    <td>
                      {formatCount(i.observation_count)} observations, {i.first_year ?? MISSING}–{i.last_year ?? MISSING}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card stack-sm">
        <h2>Coverage and limitations</h2>
        <ul>
          <li>Values are annual. Coverage varies by country, indicator and year; some years have no source value.</li>
          <li>Missing values are shown as gaps or "—" and are never converted to zero.</li>
          <li>GDP is in current US dollars (nominal, not inflation-adjusted). Unemployment is the ILO modelled estimate (% of labor force).</li>
          <li>Figures are as published by the World Bank at the time of the last pipeline run; the source may revise them later.</li>
          <li>This is a local portfolio project, not financial advice or an official statistics service.</li>
        </ul>
        <p className="muted">Application version {__APP_VERSION__}.</p>
      </section>
    </div>
  );
}
