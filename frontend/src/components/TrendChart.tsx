import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TrendResponse } from "../api/types";
import { SERIES_COLORS, missingYears, toTrendRows } from "../utils/chart";
import { formatAxis, formatValue } from "../utils/format";

/** Line chart with one series per country; missing years are gaps, never zero. */
export function TrendChart({ trend, height = 320 }: { trend: TrendResponse; height?: number }) {
  const rows = toTrendRows(trend.series);
  const unit = trend.indicator.unit;
  const gaps = trend.series
    .map((s) => ({ name: s.country_name, years: missingYears(s, rows) }))
    .filter((g) => g.years.length > 0);
  const empty = trend.series.filter((s) => s.points.length === 0).map((s) => s.country_name);

  return (
    <figure className="chart" aria-label={`${trend.indicator.name} by year, ${unit}`}>
      <div style={{ width: "100%", height }}>
        <ResponsiveContainer>
          <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
            <CartesianGrid stroke="var(--color-border)" vertical={false} />
            <XAxis dataKey="year" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={(v: number) => formatAxis(v, unit)} tick={{ fontSize: 12 }} width={72} />
            <Tooltip
              formatter={(value, name) => [formatValue(typeof value === "number" ? value : null, unit, "full"), String(name)]}
              labelFormatter={(label) => `Year ${label}`}
            />
            <Legend />
            {trend.series.map((s, i) => (
              <Line
                key={s.country_code}
                type="monotone"
                dataKey={s.country_code}
                name={s.country_name}
                stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
                strokeWidth={2}
                dot={{ r: 2 }}
                connectNulls={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="muted">
        {trend.indicator.name.includes(unit) ? trend.indicator.name : `${trend.indicator.name} (${unit})`}.
        {gaps.length > 0 && ` Gaps mark years with no source value: ${gaps.map((g) => `${g.name} (${g.years.join(", ")})`).join("; ")}.`}
        {empty.length > 0 && ` No values in this range for: ${empty.join(", ")}.`}
      </figcaption>
    </figure>
  );
}
