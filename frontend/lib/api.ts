/**
 * Typed API client for the Yuno Agent Platform backend.
 * Base URL is read from NEXT_PUBLIC_API_URL (defaults to http://localhost:8000).
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types ──────────────────────────────────────────────────────────────────────

export type RunStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface Agent {
  id: string;
  name: string;
  description: string | null;
  role: string | null;
  system_prompt: string;
  tools_enabled: string[];
  model_provider: string;
  model_name: string;
  temperature: number;
  memory_enabled: boolean;
  max_iterations: number;
  max_cost_usd: number;
  created_at: string;
  updated_at: string;
}

export interface AgentCreate {
  name: string;
  description?: string;
  role?: string;
  system_prompt: string;
  tools_enabled?: string[];
  model_provider?: string;
  model_name?: string;
  temperature?: number;
  memory_enabled?: boolean;
  max_iterations?: number;
  max_cost_usd?: number;
}

export type AgentUpdate = Partial<AgentCreate>;

export interface Workflow {
  id: string;
  name: string;
  description: string | null;
  graph_json: Record<string, unknown>;
  status: "draft" | "active" | "archived";
  cron_schedule: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowCreate {
  name: string;
  description?: string;
  graph_json?: Record<string, unknown>;
  status?: "draft" | "active" | "archived";
  cron_schedule?: string;
}

export type WorkflowUpdate = Partial<WorkflowCreate>;

export interface Run {
  id: string;
  workflow_id: string | null;
  status: RunStatus;
  trigger_channel: string | null;
  trigger_payload: Record<string, unknown> | null;
  // NOTE: error_message, total_cost_usd, and final_response are only returned
  // by GET /runs/{id}/timeline (embedded run object), NOT by GET /runs or
  // GET /runs/{id}. Treat them as optional when reading from list/single endpoints.
  error_message?: string | null;
  total_cost_usd?: number | null;
  final_response?: string | null;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
}

export interface RunStep {
  id: string;
  agent_id: string | null;
  status: string;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  started_at: string | null;
  ended_at: string | null;
}

export interface ToolCall {
  id: string;
  tool_name: string;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  created_at: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  created_at: string;
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
}

export interface RunTimeline {
  run: Run;
  steps: RunStep[];
  messages: Message[];
  tool_calls: ToolCall[];
  token_usage: TokenUsage;
}

// ── Fetch helper ───────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── Agent endpoints ────────────────────────────────────────────────────────────

export const getAgents = (): Promise<Agent[]> => apiFetch("/agents");

export const getAgent = (id: string): Promise<Agent> => apiFetch(`/agents/${id}`);

export const createAgent = (body: AgentCreate): Promise<Agent> =>
  apiFetch("/agents", { method: "POST", body: JSON.stringify(body) });

export const updateAgent = (id: string, body: AgentUpdate): Promise<Agent> =>
  apiFetch(`/agents/${id}`, { method: "PUT", body: JSON.stringify(body) });

export const deleteAgent = (id: string): Promise<void> =>
  apiFetch(`/agents/${id}`, { method: "DELETE" });

// ── Workflow endpoints ─────────────────────────────────────────────────────────

export const getWorkflows = (): Promise<Workflow[]> => apiFetch("/workflows");

export const getWorkflow = (id: string): Promise<Workflow> => apiFetch(`/workflows/${id}`);

export const createWorkflow = (body: WorkflowCreate): Promise<Workflow> =>
  apiFetch("/workflows", { method: "POST", body: JSON.stringify(body) });

export const updateWorkflow = (id: string, body: WorkflowUpdate): Promise<Workflow> =>
  apiFetch(`/workflows/${id}`, { method: "PUT", body: JSON.stringify(body) });

export const deleteWorkflow = (id: string): Promise<void> =>
  apiFetch(`/workflows/${id}`, { method: "DELETE" });

// ── Run endpoints ──────────────────────────────────────────────────────────────

export const getRunsList = (params?: {
  workflow_id?: string;
  skip?: number;
  limit?: number;
}): Promise<Run[]> => {
  const q = new URLSearchParams();
  if (params?.workflow_id) q.set("workflow_id", params.workflow_id);
  if (params?.skip !== undefined) q.set("skip", String(params.skip));
  if (params?.limit !== undefined) q.set("limit", String(params.limit));
  return apiFetch(`/runs?${q}`);
};

export const getRun = (id: string): Promise<Run> => apiFetch(`/runs/${id}`);

export const getRunTimeline = (id: string): Promise<RunTimeline> =>
  apiFetch(`/runs/${id}/timeline`);

export const triggerRun = (
  workflowId: string,
  payload?: { message?: string; trigger_payload?: Record<string, unknown> }
): Promise<Run> =>
  apiFetch(`/workflows/${workflowId}/run`, {
    method: "POST",
    body: JSON.stringify(payload ?? {}),
  });

export const cancelRun = (id: string): Promise<Run> =>
  apiFetch(`/runs/${id}/cancel`, { method: "POST" });
