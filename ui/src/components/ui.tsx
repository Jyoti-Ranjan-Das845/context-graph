import type { ReactNode } from "react";
import { KIND_LABELS, SOURCE_LABELS, nodeColor } from "../features/graph/palette";

export function SourceBadge({ source, kind }: { source: string; kind: string }) {
  return (
    <span className="badge" style={{ borderColor: nodeColor(kind, source), color: nodeColor(kind, source) }}>
      {SOURCE_LABELS[source] ?? source} · {KIND_LABELS[kind] ?? kind}
    </span>
  );
}

export function StatusPill({ tone, children }: { tone: "ok" | "warn" | "error" | "muted" | "busy"; children: ReactNode }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function ErrorNote({ message }: { message: string | null }) {
  return message ? <div className="error-note">{message}</div> : null;
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "never";
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} d ago`;
}
