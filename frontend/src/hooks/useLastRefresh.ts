import { useSyncExternalStore } from "react";
import { getLastRefresh, subscribeToRefresh } from "../api/refresh";

/** Time of the most recent successful data response, or null before the first one. */
export function useLastRefresh(): Date | null {
  return useSyncExternalStore(subscribeToRefresh, getLastRefresh, getLastRefresh);
}
