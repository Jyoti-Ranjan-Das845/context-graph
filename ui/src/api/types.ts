// Types mirroring the REST API (backend/src/context_graph/interfaces/api.py).

export interface NodeCard {
  id: string;
  kind: string;
  source: string;
  title: string;
  ref: string | null;
  url: string | null;
  updated_at: string | null;
  snippet: string;
}

export interface EdgeView {
  src: string;
  dst: string;
  kind: string;
  confidence: number;
  evidence: string | null;
  via: string | null;
}

export interface Subgraph {
  nodes: NodeCard[];
  edges: EdgeView[];
}

export interface NodeFull {
  id: string;
  kind: string;
  source: string;
  title: string;
  body: string;
  url: string | null;
  created_at: string | null;
  updated_at: string | null;
  keys: string[];
  props: Record<string, unknown>;
}

export interface Neighbor {
  direction: "in" | "out";
  edge: EdgeView;
  node: NodeCard;
}

export interface NodeDetail {
  node: NodeFull;
  neighbors: Neighbor[];
}

export interface CredentialField {
  env_key: string;
  label: string;
  secret: boolean;
  help_url: string | null;
  help_text: string;
  placeholder: string;
  managed_by: string | null;
  is_set: boolean;
  display: string | null;
}

export interface JsonSchemaProperty {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  items?: { type?: string };
  anyOf?: JsonSchemaProperty[];
  minimum?: number;
  maximum?: number;
}

export interface SourceInfo {
  id: string;
  label: string;
  configured: boolean;
  enabled: boolean;
  missing: string[];
  setup_steps: string[];
  credentials: CredentialField[];
  options: Record<string, unknown>;
  options_schema: { properties?: Record<string, JsonSchemaProperty> };
  last_pull: SourceRunStatus;
}

/** What the last sync did for one tool (written by the pipeline into the sync status). */
export interface SourceRunStatus {
  pull?: "running" | "ok" | "error" | "disabled" | "not_configured";
  message?: string;
  records?: Record<string, number>;
  items?: number;
  people?: number;
  normalize_error?: string;
  missing?: string[];
  started_at?: string;
  finished_at?: string;
}

export interface SyncStatus {
  state: "running" | "idle" | "failed" | "never_run" | "unknown";
  step?: string;
  trigger?: string;
  started_at?: string | null;
  finished_at?: string | null;
  last_success_at?: string | null;
  error?: string | null;
  sources?: Record<string, SourceRunStatus>;
  graph?: { nodes?: number; edges?: number };
  enrichment?: Record<string, unknown>;
}

export interface AppSettings {
  sync: { interval_minutes: number; start_date: string };
  enrichment: {
    enabled: boolean;
    provider: string;
    model: string | null;
    batch_size: number;
    max_items_per_sync: number;
    timeout_seconds: number;
  };
  identity: { merge_by_name: boolean };
}

export interface ScheduleStatus {
  installed: boolean;
  interval_minutes: number | null;
  plist: string;
}

export interface Stats {
  nodes: number;
  edges: number;
  by_kind: Record<string, number>;
  by_source: Record<string, number>;
  by_edge_kind: Record<string, number>;
  meta: Record<string, unknown>;
}

export interface ContextBundle {
  question: string;
  results: (NodeCard & { links: string[] })[];
}

export interface AgentInfo {
  id: string;
  label: string;
  /** The agent seems to be installed on this computer. */
  detected: boolean;
  /** The context-graph skill is in place. */
  installed: boolean;
  location: string;
}
