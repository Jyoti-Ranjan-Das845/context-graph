import { useEffect, useState } from "react";
import { api, errorMessage } from "../../api/client";
import type { AgentInfo } from "../../api/types";
import { ErrorNote, StatusPill } from "../../components/ui";
import { useAsync } from "../../hooks/useAsync";

function agentPill(agent: AgentInfo) {
  if (agent.installed) return <StatusPill tone="ok">Skill added</StatusPill>;
  if (agent.detected) return <StatusPill tone="muted">Not added</StatusPill>;
  return <StatusPill tone="muted">Not found on this computer</StatusPill>;
}

/** Add or remove the skill that teaches Claude Code and Codex the `cg` commands. */
export function AgentsCard() {
  const loaded = useAsync(() => api.agents(), []);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loaded.data) setAgents(loaded.data);
  }, [loaded.data]);

  async function toggle(agent: AgentInfo) {
    setBusy(agent.id);
    setError(null);
    try {
      const updated = await api.setAgentSkill(agent.id, !agent.installed);
      setAgents((current) => current.map((a) => (a.id === updated.id ? updated : a)));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <article className="card">
      <div className="card-body">
        <p className="muted small">
          The skill teaches the agent the <code>cg</code> commands (<code>cg ask</code>, <code>cg show</code>, <code>cg neighbors</code>…), so
          it can look up your work in any project. It only reads the graph. Same as running <code>cg agent install</code>.
        </p>
        {agents.map((agent) => (
          <div key={agent.id} className="row">
            <strong className="agent-name">{agent.label}</strong>
            {agentPill(agent)}
            <button className="secondary" disabled={busy !== null || (!agent.detected && !agent.installed)} onClick={() => toggle(agent)}>
              {busy === agent.id ? "Saving…" : agent.installed ? "Remove" : "Add skill"}
            </button>
            {agent.installed && <code className="small clip" title={agent.location}>{agent.location}</code>}
          </div>
        ))}
        <ErrorNote message={error ?? loaded.error} />
      </div>
    </article>
  );
}
