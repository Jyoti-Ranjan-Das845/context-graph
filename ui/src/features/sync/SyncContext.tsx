import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, errorMessage } from "../../api/client";
import type { SyncStatus } from "../../api/types";
import { useInterval } from "../../hooks/useAsync";

const FAST_POLL_MS = 1500;
const SLOW_POLL_MS = 10000;

interface SyncState {
  status: SyncStatus | null;
  running: boolean;
  /** A start request is on its way. */
  starting: boolean;
  error: string | null;
  start: () => Promise<void>;
}

const SyncContext = createContext<SyncState | null>(null);

/**
 * Polls the sync status for the whole app and starts syncs. Calls `onSynced` whenever any
 * sync finishes, including scheduled ones started outside the web app.
 */
export function SyncProvider({ onSynced, children }: { onSynced: () => void; children: ReactNode }) {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastFinished = useRef<string | null | undefined>(undefined);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.syncStatus());
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  const running = status?.state === "running";
  useEffect(() => void refresh(), [refresh]);
  useInterval(refresh, running ? FAST_POLL_MS : SLOW_POLL_MS);

  useEffect(() => {
    if (!status) return;
    const finished = status.finished_at ?? null;
    if (finished !== null && lastFinished.current !== undefined && finished !== lastFinished.current) onSynced();
    lastFinished.current = finished;
  }, [status, onSynced]);

  // The API answers once the sync is running (or 409 if one already is), so one refresh shows it.
  const start = useCallback(async () => {
    setStarting(true);
    setError(null);
    try {
      await api.startSync();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      await refresh();
      setStarting(false);
    }
  }, [refresh]);

  return <SyncContext.Provider value={{ status, running, starting, error, start }}>{children}</SyncContext.Provider>;
}

export function useSync(): SyncState {
  const state = useContext(SyncContext);
  if (!state) throw new Error("useSync must be used inside <SyncProvider>");
  return state;
}
