import { useEffect, useState } from "react";
import { api, errorMessage } from "../../api/client";
import type { AppSettings, ScheduleStatus } from "../../api/types";
import { useAsync } from "../../hooks/useAsync";
import { ErrorNote, StatusPill } from "../../components/ui";

/** How far back to pull, how often to sync, and whether Claude Code adds topics and decisions. */
export function SyncSettings() {
  const loaded = useAsync(() => Promise.all([api.settings(), api.schedule()]), []);
  const [draft, setDraft] = useState<AppSettings | null>(null);
  const [saved, setSaved] = useState<AppSettings | null>(null);
  const [schedule, setSchedule] = useState<ScheduleStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loaded.data) return;
    const [settings, scheduleStatus] = loaded.data;
    setDraft(settings);
    setSaved(settings);
    setSchedule(scheduleStatus);
  }, [loaded.data]);

  if (!draft || !saved) return <ErrorNote message={loaded.error} />;

  async function run(task: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await task();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const save = () =>
    run(async () => {
      const next = await api.saveSettings({ sync: draft.sync, enrichment: draft.enrichment, identity: draft.identity });
      setDraft(next);
      setSaved(next);
      setSchedule(await api.schedule());
    });
  const setScheduled = (enabled: boolean) => run(async () => setSchedule(await api.saveSchedule(enabled)));

  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  const patch = <K extends keyof AppSettings>(section: K, value: Partial<AppSettings[K]>) =>
    setDraft({ ...draft, [section]: { ...draft[section], ...value } });

  return (
    <article className="card">
      <div className="card-body">
        <div className="grid-2">
          <label className="field">
            <span>Pull data since</span>
            <input
              type="date"
              value={draft.sync.start_date.slice(0, 10)}
              onChange={(e) => e.target.value && patch("sync", { start_date: `${e.target.value}T00:00:00Z` })}
            />
            <span className="muted small">Each tool can override this in its own options.</span>
          </label>
          <label className="field">
            <span>Sync every (minutes)</span>
            <input
              type="number"
              min={5}
              max={1440}
              value={draft.sync.interval_minutes}
              onChange={(e) => patch("sync", { interval_minutes: Number(e.target.value) })}
            />
            <span className="muted small">Used by background sync.</span>
          </label>
        </div>
        <label className="toggle">
          <input type="checkbox" checked={draft.enrichment.enabled} onChange={(e) => patch("enrichment", { enabled: e.target.checked })} />
          Find topics and decisions with Claude Code. Uses your Claude plan; only new or changed text is sent.
        </label>
        <label className="toggle">
          <input
            type="checkbox"
            checked={draft.identity.merge_by_name}
            onChange={(e) => patch("identity", { merge_by_name: e.target.checked })}
          />
          Treat people with the same full name in different tools as one person.
        </label>
        <div className="row">
          <button className="primary" disabled={!dirty || busy} onClick={save}>
            Save
          </button>
        </div>
        <div className="row">
          <span>Background sync</span>
          {schedule?.installed ? (
            <>
              <StatusPill tone="ok">On · every {schedule.interval_minutes} min</StatusPill>
              <button className="secondary" disabled={busy} onClick={() => setScheduled(false)}>
                Turn off
              </button>
            </>
          ) : (
            <>
              <StatusPill tone="muted">Off</StatusPill>
              <button className="secondary" disabled={busy} onClick={() => setScheduled(true)}>
                Turn on
              </button>
            </>
          )}
          <span className="muted small">Runs even when this page is closed (macOS launchd).</span>
        </div>
        <ErrorNote message={error} />
      </div>
    </article>
  );
}
