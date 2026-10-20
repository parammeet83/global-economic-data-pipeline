# Web Application Flow

- **Project:** Global Economic Data Pipeline & Analytics Dashboard
- **Version:** 1.1
- **Last updated:** 2026-10-19
- **Decisions:** changes from v1.0 are explained in `DECISIONS.md` (referenced as `D-xx`).

## 1. Purpose

Describe how a user moves through the browser application, how each view calls the backend, and how loading, empty, and error states behave. This is a dashboard for exploring loaded public economic data and monitoring the reliability of its pipeline.

## 2. Main navigation

1. **Overview** — KPIs, latest run status, data freshness, and a small trend preview.
2. **Explore Data** — choose indicator, countries, year range, and inspect a paginated table or time series.
3. **Compare Countries** — compare selected countries for an indicator/year.
4. **Pipeline Runs** — inspect run history, counts, durations, and sanitized errors; manually trigger a run in local/demo mode.
5. **Data Quality** — inspect most recent quality summary and individual checks.
6. **About / Data Sources** — source, indicator definitions, units, update limitations, and application version.

## 3. First-time visitor flow

```text
Open web app
  -> Load dashboard summary and filter metadata
  -> If backend unreachable: show connection error and retry action
  -> If backend reachable but /health reports database unavailable (503): show database error and retry action
  -> If database is empty: show first-run empty state with setup/run guidance
  -> If data exists: display KPIs, freshness and trend preview
  -> User selects Explore Data / Compare / Runs / Quality
```

The frontend must not fabricate demo values in production views. Sample fixture data is allowed only in component tests or a clearly labeled demo mode.

## 4. Overview flow

1. Fetch `GET /api/v1/dashboard/summary`, `GET /api/v1/quality/latest`, and `GET /api/v1/runs?page=1&page_size=5`.
2. Show total countries, indicators, observations, latest successful load time, and latest run status.
3. Display a trend chart for the default indicator and countries returned in the summary's `defaults` (configured on the backend, D-26) if data exists. The frontend hard-codes no country list.
4. Display recent runs and link to their details.
5. If the most recent run failed, show a restrained warning with a link to run details; do not block access to prior valid observations.

**States:** skeleton/loading; healthy with data; empty database; partial data; API/database failure.

## 5. Explore Data flow

1. Load country and indicator options.
2. User selects indicator (required), country/countries, start year, and end year.
3. Validate `start_year <= end_year`; prevent invalid or excessive query inputs.
4. Fetch trend and/or observation rows from the backend.
5. Render chart, table, count, unit and active filter chips.
6. User changes a filter; reset pagination and re-fetch.
7. Optional export (P1) downloads only the currently filtered result set, with a row limit or streaming design if needed.

Multiple countries are sent as repeated `country_code` query parameters; paginated responses use `{items, page, page_size, total}` (D-25).

**API calls:** `GET /api/v1/indicators`, `GET /api/v1/countries`, `GET /api/v1/analytics/trend`, `GET /api/v1/observations`.

## 6. Compare Countries flow

1. Choose an indicator and observation year.
2. Select 2–10 countries (initial cap for chart readability; the exact cap can be configurable).
3. Request `GET /api/v1/analytics/country-comparison`.
4. Display a sorted bar chart and table using the indicator's unit.
5. Exclude missing values from the bars, clearly list unavailable countries, and never substitute zero.

If the API returns no values for the selection, show a clear empty state suggesting another year or indicator.

## 7. Pipeline Runs flow

1. Fetch `GET /api/v1/runs?page=1&page_size=20`.
2. Display status, started/finished time, duration (elapsed time for `running` rows), records extracted/loaded/rejected, trigger type, and a details link.
3. Selecting a row calls `GET /api/v1/runs/{run_id}`.
4. Detail view shows stage counts (extracted, rejected, null-skipped, duplicates dropped, load-ready, loaded, inserted, value changed; definitions in `Backend_DB_Schema.md` §3.3), quality checks, and sanitized error summary.
5. The local/demo user can press **Run pipeline**. Show a confirmation dialog describing that API requests and database writes will occur.
6. On confirmation, POST to `/api/v1/pipeline/run`; disable the button while a run is starting. Responses (D-23):
   - **202** `{run_id, status: "running", status_url}`: the run has been recorded and is executing in the background.
   - **409** `run_in_progress` (database-enforced overlap guard): explain a run is already in progress and link to it.
   - **403**: manual trigger is disabled in this environment.
7. Show the accepted run ID and poll `GET /api/v1/runs/{run_id}` every 3 seconds until a terminal status (D-24). Stop polling on completion or failure; after 10 minutes stop and show "still running — check Pipeline Runs later".
8. Refresh dashboard and history after completion.

Status/date filters on the run list are P1 (D-30).

**Safety:** the trigger control is for local/demo operation only in the MVP. It must not be publicly exposed without authentication and operational safeguards. Background execution limitation: if the API server stops or reloads during a run, that run is abandoned and later marked `failed` by stale-run recovery (D-20); the UI must show it as running (with elapsed time) until then, never as succeeded.

## 8. Data Quality flow

1. Fetch `GET /api/v1/quality/latest`. It returns the most recent **terminal** run (`success`, `partial_success` or `failed`) and its checks; if none exists, show the empty state (D-17).
2. Show run ID, timestamp, overall status and counts.
3. Show each check's name, status, records checked, records failed and details.
4. Explain the meaning of warnings and the policy for missing source observations: null-skipped rows are source gaps (warning), rejected rows are malformed data (failed check), identical duplicates are dropped (warning), conflicting duplicates are a failed check.
5. Link to the associated pipeline run.

Never show a green all-clear badge if checks failed or if the run itself failed. Distinguish source missingness from data corruption.

## 9. API and UI error handling

| Situation | UI behavior |
|---|---|
| API request pending | Show skeleton or inline spinner; avoid blocking entire app when unnecessary |
| Empty database | Explain that no observations are loaded and provide setup/run guidance for local demo |
| No matching filter results | Keep filters visible and explain no records matched the selection |
| Source gaps/null values | Show gaps or unavailable entries, not numeric zeros |
| Backend unreachable | Show a clear connection error and Retry action |
| Database unavailable (`/health` 503 or API 503) | Show a database error and Retry action; do not show empty-data guidance |
| Pipeline trigger returns conflict (409) | Explain a run is already in progress and link to that run |
| Pipeline trigger refused (403) | Show the API's message: manual runs are disabled, or the request is not local (another machine, or an unconfigured proxy) |
| Pipeline run fails | Show failure status and sanitized error summary; retain access to older data |
| Invalid filter input | Display inline validation; do not send a malformed request |

## 10. Navigation and URL behavior

- Use a stable sidebar or top navigation with a visible active route.
- **P1:** preserve key explore filters in query parameters so links can be shared during a demo (D-30).
- Detail routes should include run ID but must not expose secrets.
- Refreshing a page must recover its route (P0); recovering filters after refresh depends on the P1 query-parameter work.

## 11. Responsive behavior

Scope per D-29:

- **P0, desktop:** persistent sidebar, multi-column KPI cards, chart and run table.
- **P0, narrow widths:** no critical control clipped at 320 px; KPI cards and filters fall back to a single column; tables scroll horizontally.
- **P1, tablet:** collapsible sidebar, 2-column KPI grid, stacked charts.
- **P1, mobile:** compact navigation and card-based row detail.

## 12. Accessibility and interaction

- All interactive controls work by keyboard and have visible focus states.
- Inputs have labels; icons are not the only way to identify an action.
- Status indicators include text, not color alone.
- Charts should include accessible titles/labels and a table alternative for key values.
- Error messages state what failed and what action the user can take.
