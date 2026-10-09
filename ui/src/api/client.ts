import type {
  AgentInfo,
  AppSettings,
  ContextBundle,
  NodeCard,
  NodeDetail,
  ScheduleStatus,
  SourceInfo,
  Stats,
  Subgraph,
  SyncStatus,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

const q = (params: Record<string, string | number | string[] | undefined>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue;
    for (const v of Array.isArray(value) ? value : [value]) search.append(key, String(v));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
};

const node = (id: string) => `/api/nodes/${encodeURIComponent(id)}`;

export const api = {
  graph: (filters: { kinds?: string[]; sources?: string[] } = {}) => request<Subgraph>(`/api/graph${q(filters)}`),
  search: (query: string, limit = 25) => request<NodeCard[]>(`/api/search${q({ q: query, limit })}`),
  context: (query: string) => request<ContextBundle>(`/api/context${q({ q: query })}`),
  node: (id: string) => request<NodeDetail>(node(id)),
  neighbors: (id: string, depth = 1) => request<Subgraph>(`${node(id)}/neighbors${q({ depth })}`),
  path: (src: string, dst: string) => request<Subgraph>(`/api/path${q({ src, dst })}`),
  stats: () => request<Stats>("/api/stats"),

  sources: () => request<SourceInfo[]>("/api/sources"),
  checkSource: (id: string) => request<{ ok: boolean; message: string }>(`/api/sources/${id}/check`, { method: "POST" }),
  saveCredentials: (id: string, values: Record<string, string>) =>
    request<SourceInfo>(`/api/sources/${id}/credentials`, { method: "PUT", body: JSON.stringify({ values }) }),
  saveOptions: (id: string, values: Record<string, unknown>) =>
    request<SourceInfo>(`/api/sources/${id}/options`, { method: "PUT", body: JSON.stringify({ values }) }),
  gmailSignIn: () => request<SourceInfo>("/api/sources/gmail/signin", { method: "POST" }),
  slackCreateAppUrl: () => request<{ url: string }>("/api/sources/slack/create-app-url"),

  settings: () => request<AppSettings>("/api/settings"),
  saveSettings: (patch: Partial<AppSettings>) => request<AppSettings>("/api/settings", { method: "PUT", body: JSON.stringify(patch) }),
  schedule: () => request<ScheduleStatus>("/api/schedule"),
  saveSchedule: (enabled: boolean, interval_minutes?: number) =>
    request<ScheduleStatus>("/api/schedule", { method: "PUT", body: JSON.stringify({ enabled, interval_minutes }) }),

  agents: () => request<AgentInfo[]>("/api/agents"),
  setAgentSkill: (id: string, installed: boolean) =>
    request<AgentInfo>(`/api/agents/${id}`, { method: "PUT", body: JSON.stringify({ installed }) }),

  syncStatus: () => request<SyncStatus>("/api/sync/status"),
  startSync: (options: { pull?: boolean; enrich?: boolean | null } = {}) =>
    request<{ started: boolean }>("/api/sync", { method: "POST", body: JSON.stringify(options) }),
};

/** A readable message for anything a failed request or promise can throw. */
export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
