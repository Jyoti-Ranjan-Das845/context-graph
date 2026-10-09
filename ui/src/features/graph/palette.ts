// One place for how tools and node kinds look, used by the graph canvas, legends and badges.

export const SOURCE_COLORS: Record<string, string> = {
  github: "#6e7781",
  linear: "#5e6ad2",
  jira: "#2684ff",
  notion: "#9b9a97",
  slack: "#e01e5a",
  gmail: "#ea4335",
  code: "#2da44e",
  derived: "#d4a017",
};

export const KIND_COLORS: Record<string, string> = {
  person: "#f59e0b",
  topic: "#14b8a6",
  decision: "#8b5cf6",
};

export const SOURCE_LABELS: Record<string, string> = {
  github: "GitHub",
  linear: "Linear",
  jira: "Jira",
  notion: "Notion",
  slack: "Slack",
  gmail: "Gmail",
  code: "Code",
  derived: "People & meaning",
};

export const KIND_LABELS: Record<string, string> = {
  person: "Person",
  repository: "Repository",
  issue: "Issue",
  pull_request: "Pull request",
  commit: "Commit",
  comment: "Comment",
  project: "Project",
  channel: "Channel",
  message: "Message",
  page: "Page",
  email_thread: "Email thread",
  email: "Email",
  file: "File",
  symbol: "Function",
  topic: "Topic",
  decision: "Decision",
};

export const KIND_SHAPES: Record<string, string> = {
  person: "ellipse",
  repository: "barrel",
  issue: "round-rectangle",
  pull_request: "round-tag",
  commit: "round-triangle",
  comment: "ellipse",
  project: "round-hexagon",
  channel: "round-hexagon",
  message: "ellipse",
  page: "round-rectangle",
  email_thread: "round-hexagon",
  email: "ellipse",
  file: "rectangle",
  symbol: "round-diamond",
  topic: "round-octagon",
  decision: "diamond",
};

export const KIND_SIZE: Record<string, number> = {
  person: 34,
  repository: 34,
  issue: 30,
  pull_request: 30,
  page: 30,
  channel: 28,
  email_thread: 28,
  project: 28,
  decision: 22,
  topic: 20,
  message: 18,
  email: 18,
  comment: 16,
  commit: 18,
  file: 20,
  symbol: 16,
};

export function nodeColor(kind: string, source: string): string {
  return KIND_COLORS[kind] ?? SOURCE_COLORS[source] ?? "#888";
}

/** Groups of node kinds the graph view can show or hide together. */
export const LAYERS = {
  meaning: new Set(["topic", "decision"]),
  code: new Set(["file", "symbol"]),
  people: new Set(["person"]),
};

export type Layer = keyof typeof LAYERS;

export const LAYER_LABELS: Record<Layer, string> = {
  meaning: "Topics & decisions",
  code: "Code",
  people: "People",
};
