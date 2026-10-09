import type { SyncStatus } from "../../api/types";
import { StatusPill, timeAgo } from "../../components/ui";
import { SOURCE_LABELS } from "../graph/palette";
import { useSync } from "./SyncContext";

/** Tools whose last pull or read failed, so the user knows which one to fix in Setup. */
export function failedTools(status: SyncStatus | null): string[] {
  return Object.entries(status?.sources ?? {})
    .filter(([, run]) => run.pull === "error" || run.normalize_error)
    .map(([id]) => SOURCE_LABELS[id] ?? id);
}

/** One-line sync state, shared by the top bar and the Setup page. */
export function SyncState() {
  const { status, running } = useSync();
  if (running) return <StatusPill tone="busy">Syncing · {status?.step}</StatusPill>;
  if (status?.state === "failed")
    return (
      <>
        <StatusPill tone="error">Last sync failed</StatusPill>
        <span className="small error-text clip" title={status.error ?? undefined}>
          {status.error}
        </span>
      </>
    );
  if (!status || status.state === "never_run") return <StatusPill tone="muted">Not synced yet</StatusPill>;
  return <StatusPill tone="ok">Synced {timeAgo(status.last_success_at)}</StatusPill>;
}

export function SyncButton() {
  const { running, starting, start } = useSync();
  return (
    <button className="primary" onClick={start} disabled={running || starting}>
      {running || starting ? "Syncing…" : "Sync now"}
    </button>
  );
}

export function SyncBar() {
  const { status, running, error } = useSync();
  const failed = failedTools(status);
  return (
    <div className="syncbar">
      <SyncState />
      {!running && failed.length > 0 && (
        <a href="#/setup" className="small error-text">
          {failed.join(", ")} failed
        </a>
      )}
      {error && <span className="small error-text">{error}</span>}
      <SyncButton />
    </div>
  );
}
