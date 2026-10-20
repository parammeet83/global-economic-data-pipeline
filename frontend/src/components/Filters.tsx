import type { Country, Indicator } from "../api/types";

export function IndicatorSelect({
  indicators,
  value,
  onChange,
  id = "indicator",
}: {
  indicators: Indicator[];
  value: string;
  onChange: (code: string) => void;
  id?: string;
}) {
  return (
    <label className="field" htmlFor={id}>
      Indicator (required)
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} required>
        {indicators.map((i) => (
          <option key={i.indicator_code} value={i.indicator_code}>
            {i.name}
          </option>
        ))}
      </select>
    </label>
  );
}

export function CountryPicker({
  countries,
  selected,
  onChange,
  legend = "Countries",
}: {
  countries: Country[];
  selected: string[];
  onChange: (codes: string[]) => void;
  legend?: string;
}) {
  const toggle = (code: string) =>
    onChange(selected.includes(code) ? selected.filter((c) => c !== code) : [...selected, code]);
  return (
    <fieldset>
      <legend>{legend}</legend>
      <div className="checkbox-grid">
        {countries.map((c) => (
          <label key={c.country_code}>
            <input type="checkbox" checked={selected.includes(c.country_code)} onChange={() => toggle(c.country_code)} />
            {c.name}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function YearInput({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="field" htmlFor={id}>
      {label}
      <input id={id} type="number" inputMode="numeric" min={1900} max={2200} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <nav className="pagination" aria-label="Pagination">
      <span className="muted">
        Page {page} of {pages} · {total.toLocaleString("en-US")} rows
      </span>
      <span className="chips">
        <button type="button" className="button secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Previous
        </button>
        <button type="button" className="button secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Next
        </button>
      </span>
    </nav>
  );
}
