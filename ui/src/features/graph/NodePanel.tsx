import { useMemo, useState } from "react";
import { api } from "../../api/client";
import type { Neighbor } from "../../api/types";
import { useAsync } from "../../hooks/useAsync";
import { ErrorNote, SourceBadge, timeAgo } from "../../components/ui";
import { KIND_LABELS, SOURCE_LABELS } from "./palette";

const OUT_LABELS: Record<string, string> = {
  authored: "Authored",
  assigned_to: "Assigned to",
  part_of: "Part of",
  reply_to: "Reply to",
  references: "References",
  fixes: "Fixes",
  changes: "Changes",
  contains: "Contains",
  calls: "Calls",
  imports: "Imports",
  mentions: "Mentions",
  decides: "Decides",
  about: "About",
};

const IN_LABELS: Record<string, string> = {
  authored: "Author",
  assigned_to: "Assigned items",
  part_of: "Contains",
  reply_to: "Replies",
  references: "Referenced by",
  fixes: "Fixed by",
  changes: "Changed by",
  contains: "Defined in",
  calls: "Called by",
  imports: "Imported by",
  mentions: "Mentioned in",
  decides: "Decided in",
  about: "Decisions",
};

const BODY_PREVIEW = 700;

export function NodePanel({ nodeId, onSelect, onClose }: { nodeId: string; onSelect: (id: string) => void; onClose?: () => void }) {
  const { data, error, loading } = useAsync(() => api.node(nodeId), [nodeId]);
  const [expanded, setExpanded] = useState(false);

  const groups = useMemo(() => {
    const out = new Map<string, Neighbor[]>();
    for (const neighbor of data?.neighbors ?? []) {
      const labels = neighbor.direction === "out" ? OUT_LABELS : IN_LABELS;
      const label = labels[neighbor.edge.kind] ?? neighbor.edge.kind;
      out.set(label, [...(out.get(label) ?? []), neighbor]);
    }
    return [...out.entries()];
  }, [data]);

  if (error) return <aside className="panel"><ErrorNote message={error} /></aside>;
  if (loading || !data) return <aside className="panel"><div className="muted">Loading…</div></aside>;

  const { node } = data;
  const ref = typeof node.props.ref === "string" ? node.props.ref : null;
  const body = node.body ?? "";
  const shown = expanded || body.length <= BODY_PREVIEW ? body : `${body.slice(0, BODY_PREVIEW)}…`;
  const extraProps = Object.entries(node.props).filter(([k, v]) => k !== "ref" && v !== null && v !== "" && !(Array.isArray(v) && !v.length));

  return (
    <aside className="panel">
      <div className="panel-head">
        <SourceBadge source={node.source} kind={node.kind} />
        {onClose && <button className="icon-button" onClick={onClose} aria-label="Close">×</button>}
      </div>
      <h2 className="panel-title">
        {ref && <span className="ref">{ref}</span>} {node.title}
      </h2>
      <div className="panel-meta">
        {node.updated_at && <span>Updated {timeAgo(node.updated_at)}</span>}
        {node.url && (
          <a href={node.url} target="_blank" rel="noreferrer">
            Open in {node.source === "code" ? "GitHub" : SOURCE_LABELS[node.source] ?? node.source} ↗
          </a>
        )}
      </div>

      {body && (
        <div className="panel-body">
          <pre>{shown}</pre>
          {body.length > BODY_PREVIEW && (
            <button className="link-button" onClick={() => setExpanded(!expanded)}>{expanded ? "Show less" : "Show all"}</button>
          )}
        </div>
      )}

      {extraProps.length > 0 && (
        <dl className="props">
          {extraProps.map(([key, value]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>{Array.isArray(value) ? value.join(", ") : String(value)}</dd>
            </div>
          ))}
        </dl>
      )}

      <h3 className="panel-section">Connections ({data.neighbors.length})</h3>
      {groups.map(([label, neighbors]) => (
        <section key={label} className="neighbor-group">
          <h4>{label}</h4>
          <ul>
            {neighbors.map((n) => (
              <li key={`${n.edge.kind}-${n.node.id}-${n.direction}`}>
                <button className="neighbor" onClick={() => onSelect(n.node.id)} title={n.edge.evidence ?? undefined}>
                  <span className="neighbor-kind">{KIND_LABELS[n.node.kind] ?? n.node.kind}</span>
                  <span className="neighbor-title">{n.node.ref ? `${n.node.ref} · ` : ""}{n.node.title}</span>
                  {n.edge.confidence < 1 && <span className="confidence">{Math.round(n.edge.confidence * 100)}%</span>}
                </button>
                {n.edge.evidence && <div className="evidence">“{n.edge.evidence}”</div>}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </aside>
  );
}
