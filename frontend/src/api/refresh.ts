// Tracks when dashboard data was last retrieved successfully from the API (UIUX spec §3).
// Only real successful data responses record a refresh; nothing here invents a time.

type Listener = () => void;

let lastRefresh: Date | null = null;
const listeners = new Set<Listener>();

export function recordRefresh(at: Date = new Date()): void {
  lastRefresh = at;
  listeners.forEach((listener) => listener());
}

export function getLastRefresh(): Date | null {
  return lastRefresh;
}

export function subscribeToRefresh(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Test helper: forget any recorded refresh. */
export function resetRefresh(): void {
  lastRefresh = null;
  listeners.forEach((listener) => listener());
}
