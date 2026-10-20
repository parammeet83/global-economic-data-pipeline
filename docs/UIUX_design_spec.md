# UI/UX Design Specification

- **Project:** Global Economic Data Pipeline & Analytics Dashboard
- **Version:** 1.1
- **Last updated:** 2026-10-19
- **Decisions:** changes from v1.0 are explained in `DECISIONS.md` (referenced as `D-xx`).

## 1. Design direction

Create a clean, credible analytics console with an engineering/observability feel. The interface should prioritize readable data, clear units, and run status over decoration. Use a dark navy sidebar or header paired with a light neutral workspace and a small yellow/amber accent inspired by the provided project reference. Avoid excessive gradients, glass effects, animated backgrounds, or decorative charts.

## 2. Target user and primary tasks

The primary user is a student demonstrating the project to a technical reviewer. The interface must make it easy to answer:

- What data is loaded?
- Which countries and indicators are represented?
- What changed over time?
- When did the pipeline last run?
- Did the last run succeed, and what did validation report?
- Can the run be repeated without duplicating observations?

## 3. Layout and navigation

### Desktop frame
- App shell: fixed left sidebar approximately 232–256 px wide (a collapsible sidebar is P1, D-29).
- Main content: fluid width with a max readable content width around 1440 px.
- Top bar: page title, breadcrumb where useful, last refresh time, and a compact backend health indicator.
- Main content padding: 24 px desktop; 16 px tablet; 12–16 px mobile.
- Use an 8 px spacing scale where practical.

### Sidebar items
- Overview
- Explore Data
- Compare Countries
- Pipeline Runs
- Data Quality
- About & Sources

Place project mark/title at the top and a compact version/source label at the bottom. Active navigation must be apparent without color alone.

## 4. Visual tokens

Implement tokens as plain CSS custom properties (no CSS framework in the MVP, D-03) rather than scattering literal values.

| Token | Guidance |
|---|---|
| `color.brand.navy` | Deep navy for sidebar, primary headings, and key structure (approx. `#17365D`) |
| `color.brand.blue` | Medium blue for primary interactive controls and chart series |
| `color.accent.amber` | Amber/yellow accent for a primary highlight or running/attention cue (approx. `#F4C542`) |
| `color.surface` | White or near-white cards (`#FFFFFF`) |
| `color.canvas` | Very light cool gray workspace (`#F5F7FA`) |
| `color.text.primary` | High-contrast dark text (`#17212F`) |
| `color.text.secondary` | Muted slate text, still meeting contrast needs |
| `color.border` | Light neutral borders; avoid heavy card outlines |
| `status.success` | Green with explicit text label |
| `status.warning` | Amber with explicit text label |
| `status.error` | Red with explicit text label |
| `status.running` | Blue with explicit text label/spinner |

Confirm contrast ratios during implementation; these are directional tokens, not a substitute for accessibility testing. Status color must never be the only indicator.

## 5. Typography

- Use a modern sans-serif system stack or one lightweight web font.
- Page title: 24–30 px, semibold.
- Section title: 16–20 px, semibold.
- KPI number: 26–32 px, semibold; label 12–14 px.
- Body and table text: 14–16 px.
- Supporting metadata: 12–13 px, with readable contrast.
- Use tabular numerals for KPI values, durations and dates when supported.
- Avoid long paragraphs inside dashboard cards.

## 6. Component specifications

### KPI card
- Label, primary value, short contextual line or timestamp.
- Optional small icon, but do not make icon the label.
- Values: Countries, Indicators, Observations, Last successful load.
- Use skeleton placeholders while fetching; use `—` for unavailable values, not a fabricated zero.

### Filter panel
- Indicator select (required), country multi-select, year range, Apply/reset controls if applying filters explicitly.
- Display units after indicator selection (units come from the backend's indicator list, configured per D-09).
- Validate year ranges inline.
- On mobile, stack controls into a single column.

### Charts
- Trend: line chart with years on x-axis and units-aware y-axis; tooltip displays country, year, value, unit.
- Comparison: sorted bar chart for selected country/year; include a table alternative.
- Use consistent colors by country within the same view; do not imply semantic meaning through color alone.
- Missing values appear as gaps or absent bars with a clear explanation—not zero-filled values.
- Provide chart title, axis labels, tooltip and a concise empty state.

### Data table
- Sticky column header for longer tables when practical.
- Right-align numeric values and use locale-aware number formatting.
- Display observation year, country, indicator, value, unit, and ingested timestamp when relevant.
- Server-side pagination; stable sort and current filter indicators.
- Empty, loading and failure states must not collapse the layout unexpectedly.

### Run status
- Text values: Running, Success, Partial success, Failed.
- Include run ID (shortened for display, full ID in details/copy action), trigger type (CLI, API, Scheduler), duration (elapsed time while running), and row counts.
- Run detail shows the full count breakdown: extracted, rejected, null-skipped, duplicates dropped, load-ready, loaded, inserted, value changed (`Backend_DB_Schema.md` §3.3). Label "inserted" and "value changed" clearly so a rerun with `0` / `0` reads as evidence of idempotency, not as a failure.
- Failure details should be concise and sanitized; show a separate technical detail area only when appropriate.

### Data quality list
- Check name, status, records checked, records failed, and expandable details.
- Explain difference between missing source observations (null-skipped, a warning), malformed/rejected rows (a failed check), and dropped duplicates.
- Present counts with units/context, not just decorative scores.

### Buttons
- Primary: one principal action per view (for example, Apply filters or Run pipeline).
- Secondary: refresh, reset, inspect details.
- Destructive/side-effect action: running the pipeline requires confirmation and shows the effects.
- Disable buttons during in-flight actions and show progress text.

## 7. Required pages

### Overview
- Page header and health/freshness line.
- Four KPI cards.
- Indicator trend preview.
- Recent pipeline runs (3–5 records).
- Latest quality status.

### Explore Data
- Filter panel.
- Trend chart.
- Observation table with pagination.
- Current result count and CSV export only if export is implemented.

### Compare Countries
- Indicator and year selection.
- Country selection capped to a readable number.
- Comparison bar chart plus table.
- Missing-country note.

### Pipeline Runs
- Run pipeline control (local/demo only), with confirmation dialog; handles 202 (show run ID and poll), 409 (run already in progress) and 403 (disabled).
- Filters by status/date: P1 (D-30).
- Run table with status, time, duration, load/reject counts.
- Run detail page/panel with errors and quality results.

### Data Quality
- Latest run summary.
- Check-result table/list.
- Link to run details and clear explanation of warnings.

### About & Sources
- Explain the World Bank data source and API link.
- List the three indicator codes and definitions.
- Show unit, coverage caveats, application version, and the fact that some years may be missing.

## 8. Interaction states

Every data-backed component must specify:

1. Loading: skeleton or inline spinner.
2. Success: real data with selected filters and last refresh metadata where relevant.
3. Empty: clear reason or next action.
4. Error: actionable message with Retry where safe.
5. Partial: show available results and identify what is incomplete.

Never show a green success state if the underlying API request or data-quality checks failed.

## 9. Responsive breakpoints

Suggested targets:
- Mobile: below 640 px.
- Tablet: 640–1023 px.
- Desktop: 1024 px and above.

P0 (D-29): the desktop layout is the primary target, and no critical control may be clipped at 320 px width. Tables may scroll horizontally, but filters and key status must remain usable. Tuned tablet/mobile layouts (collapsible sidebar, card-based rows) are P1.

## 10. Accessibility requirements

- Native buttons, links, labels, selects and form controls where possible.
- Keyboard navigation and visible focus rings.
- Meaningful page headings and accessible chart descriptions.
- Status text in addition to status colors.
- Minimum comfortable hit area and sufficient contrast.
- Do not use color as the only mechanism to compare series or identify validation status.

## 11. Definition of design completion

- All six pages/areas are implemented or explicitly marked P1/P2 in scope.
- Each page has loading, empty, error, and success states where applicable.
- Filter controls work with the API and URL behavior is coherent.
- Values and units match backend responses.
- Layout verified at desktop width and checked for clipping at 320 px (P0); tablet and mobile layouts verified when the P1 responsive work is done.
- No fake production data or misleading success states.
