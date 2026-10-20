import type { QualityCheck, RunSummary } from "../api/types";

export interface Verdict {
  status: "passed" | "warning" | "failed" | "none";
  label: string;
}

/** Overall quality verdict. Never "passed" when the run failed or any check failed. */
export function qualityVerdict(run: RunSummary | null, checks: QualityCheck[]): Verdict {
  if (!run) return { status: "none", label: "No finished run yet" };
  if (run.status === "failed") return { status: "failed", label: "Latest run failed" };
  if (checks.some((c) => c.status === "failed")) return { status: "failed", label: "Some checks failed" };
  if (run.status === "partial_success" || checks.some((c) => c.status === "warning")) {
    return { status: "warning", label: "Passed with warnings" };
  }
  return { status: "passed", label: "All checks passed" };
}
