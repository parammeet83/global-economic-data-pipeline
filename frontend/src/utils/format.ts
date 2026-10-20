// Display formatting. `null`/`undefined` always render as an em dash, never as 0.

export const MISSING = "—";

const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 });
const full = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

const isMissing = (value: number | null | undefined): value is null | undefined =>
  value === null || value === undefined || Number.isNaN(value);

export function formatCount(value: number | null | undefined): string {
  return isMissing(value) ? MISSING : integer.format(value);
}

/** Unit-aware value: "US$2.68T", "1.45B people", "4.17%". */
export function formatValue(value: number | null | undefined, unit: string, mode: "compact" | "full" = "compact"): string {
  if (isMissing(value)) return MISSING;
  const fmt = mode === "compact" ? compact : full;
  const lower = unit.toLowerCase();
  if (lower.includes("us$")) return `US$${fmt.format(value)}`;
  if (lower.startsWith("%")) return `${full.format(value)}%`;
  if (lower === "people") return `${fmt.format(value)} people`;
  return unit ? `${fmt.format(value)} ${unit}` : fmt.format(value);
}

/** Short axis tick label without the unit text. */
export function formatAxis(value: number, unit: string): string {
  const lower = unit.toLowerCase();
  if (lower.startsWith("%")) return `${full.format(value)}%`;
  if (lower.includes("us$")) return `US$${compact.format(value)}`;
  return compact.format(value);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return MISSING;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? MISSING : date.toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "2-digit" });
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return MISSING;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? MISSING : date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return MISSING;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return MISSING;
  return date.toLocaleString("en-GB", { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function formatDuration(seconds: number | null | undefined): string {
  if (isMissing(seconds)) return MISSING;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} min ${Math.round(seconds - minutes * 60)} s`;
}

export function elapsedSince(iso: string, now: Date = new Date()): number {
  return Math.max(0, (now.getTime() - new Date(iso).getTime()) / 1000);
}

export const shortId = (id: string) => id.slice(0, 8);

export const STATUS_LABELS: Record<string, string> = {
  running: "Running",
  success: "Success",
  partial_success: "Partial success",
  failed: "Failed",
  passed: "Passed",
  warning: "Warning",
};

export const TRIGGER_LABELS: Record<string, string> = { cli: "CLI", api: "API", scheduler: "Scheduler" };

export function humanize(name: string): string {
  const text = name.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
