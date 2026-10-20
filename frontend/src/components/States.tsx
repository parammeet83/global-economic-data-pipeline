import type { ReactNode } from "react";
import type { ApiError } from "../api/client";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="state state-loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {label}
    </div>
  );
}

export function SkeletonBlock({ height = 120 }: { height?: number }) {
  return <div className="skeleton" style={{ height }} aria-hidden="true" />;
}

/** Explains what failed and offers a retry. Never shows raw server details. */
export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  let title = "Something went wrong";
  if (error.kind === "network") title = "Cannot reach the backend";
  else if (error.isDatabaseUnavailable) title = "Database unavailable";
  else if (error.status === 422) title = "Invalid request";
  else if (error.status === 404) title = "Not found";
  return (
    <div className="state state-error" role="alert">
      <strong>{title}</strong>
      <p>{error.message}</p>
      {error.kind === "network" && <p className="muted">Start the API with <code>uvicorn src.main:app</code> in <code>backend/</code>.</p>}
      {onRetry && (
        <button type="button" className="button secondary" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state state-empty">
      <strong>{title}</strong>
      {children && <div className="muted">{children}</div>}
    </div>
  );
}
