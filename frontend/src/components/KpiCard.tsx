export function KpiCard({ label, value, context }: { label: string; value: string; context?: string }) {
  return (
    <div className="card kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {context && <div className="kpi-context">{context}</div>}
    </div>
  );
}
