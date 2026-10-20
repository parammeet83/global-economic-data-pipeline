import { STATUS_LABELS } from "../utils/format";

const ICONS: Record<string, string> = {
  running: "◔",
  success: "✓",
  passed: "✓",
  partial_success: "!",
  warning: "!",
  failed: "✕",
};

/** Status is always written out in text; colour is only a secondary cue. */
export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`badge badge-${status}`}>
      <span aria-hidden="true" className="badge-icon">
        {ICONS[status] ?? "•"}
      </span>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}
