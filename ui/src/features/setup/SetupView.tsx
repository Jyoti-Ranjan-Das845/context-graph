import { useEffect, useState, type ReactNode } from "react";
import { api } from "../../api/client";
import type { SourceInfo } from "../../api/types";
import { useAsync } from "../../hooks/useAsync";
import { ErrorNote } from "../../components/ui";
import { SyncButton, SyncState } from "../sync/SyncBar";
import { useSync } from "../sync/SyncContext";
import { AgentsCard } from "./AgentsCard";
import { SourceCard } from "./SourceCard";
import { SyncSettings } from "./SyncSettings";

function Step({ number, title, hint, children }: { number: number; title: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <section className="step">
      <header className="step-head">
        <span className="step-number">{number}</span>
        <div>
          <h3>{title}</h3>
          {hint && <p className="muted small">{hint}</p>}
        </div>
      </header>
      {children}
    </section>
  );
}

function FirstSync() {
  const { status } = useSync();
  const nodes = status?.graph?.nodes;
  return (
    <article className="card">
      <div className="card-body">
        <div className="row">
          <SyncState />
          <SyncButton />
          {nodes !== undefined && (
            <span className="muted small">
              {nodes} items, {status?.graph?.edges ?? 0} links · <a href="#/graph">open the graph →</a>
            </span>
          )}
        </div>
      </div>
    </article>
  );
}

/** The checklist `cg setup` opens: tools, sync choices, first sync, agents. `version` reloads tool status after each sync. */
export function SetupView({ version }: { version: number }) {
  const sources = useAsync(() => api.sources(), [version]);
  const [list, setList] = useState<SourceInfo[]>([]);

  useEffect(() => {
    if (sources.data) setList(sources.data);
  }, [sources.data]);

  const replace = (updated: SourceInfo) => setList((current) => current.map((s) => (s.id === updated.id ? updated : s)));
  const ready = list.filter((s) => s.configured && s.enabled).length;

  return (
    <div className="page">
      <div className="page-head">
        <h2>Setup</h2>
        <p className="muted">Keys are saved only on this computer and are never shown in full.</p>
      </div>

      <Step number={1} title="Connect your tools" hint={`${ready} of ${list.length} ready. Skip any tool you don't use.`}>
        <ErrorNote message={sources.error} />
        <div className="cards">
          {list.map((source) => (
            <SourceCard key={source.id} source={source} onChange={replace} />
          ))}
        </div>
      </Step>

      <Step number={2} title="Choose what to sync and how often">
        <SyncSettings />
      </Step>

      <Step number={3} title="Sync" hint="The first sync takes about a minute. The Graph tab fills in when it is done.">
        <FirstSync />
      </Step>

      <Step number={4} title="Connect your AI agents" hint="Optional. Lets Claude Code and Codex answer questions about your work.">
        <AgentsCard />
      </Step>
    </div>
  );
}
