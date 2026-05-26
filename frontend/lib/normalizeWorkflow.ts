/**
 * normalizeWorkflow.ts
 *
 * The backend stores graph_json in a "compiler-native" format:
 *   - node type "start" instead of "trigger"
 *   - agent nodes: data.agent = "intake_agent" (slug, not UUID)
 *   - condition nodes: data.cases = { key: target, ... } instead of operator/value
 *   - edges: data.condition = "true"/"false"/"default" instead of sourceHandle
 *
 * This module converts that format into the ReactFlow-native format our
 * canvas and node components expect, so the builder renders configured
 * values instead of "Not configured."
 *
 * Used only on load — we never write back in this format.
 */

import type { Node, Edge } from "@xyflow/react";
import type { Agent } from "./api";

// ── Edge normalization ────────────────────────────────────────────────────────

/**
 * Map backend edge condition labels to ReactFlow sourceHandle IDs.
 * - "true" / "false"  → direct passthrough
 * - "default"         → "false" (the fallback branch of a condition)
 * - anything else     → "true" (a specific matching case = the true branch)
 */
function conditionToHandle(condition: string | undefined): string | undefined {
  if (!condition) return undefined;
  if (condition === "true") return "true";
  if (condition === "false" || condition === "default") return "false";
  return "true"; // specific case match = true branch
}

export function normalizeEdges(rawEdges: Edge[]): Edge[] {
  return rawEdges.map((edge) => {
    const cond = (edge.data as Record<string, unknown> | undefined)?.condition as string | undefined;
    const sourceHandle = conditionToHandle(cond);
    return {
      ...edge,
      sourceHandle: edge.sourceHandle ?? sourceHandle ?? undefined,
      animated: true,
      style: { stroke: "#8b5cf6", strokeWidth: 2 },
    };
  });
}

// ── Node normalization ─────────────────────────────────────────────────────────

/**
 * Build a name-slug → Agent lookup map.
 * Handles both "intake_agent" and "Intake Agent" variants.
 */
function buildAgentMap(agents: Agent[]): Map<string, Agent> {
  const map = new Map<string, Agent>();
  for (const a of agents) {
    // exact name
    map.set(a.name, a);
    map.set(a.name.toLowerCase(), a);
    // snake_case slug (e.g. "intake_agent" → "intake agent" → match)
    map.set(a.name.toLowerCase().replace(/\s+/g, "_"), a);
    // strip "_agent" suffix (e.g. "intake_agent" → "intake")
    const stripped = a.name.toLowerCase().replace(/_agent$/, "").replace(/\s+agent$/i, "");
    map.set(stripped, a);
  }
  return map;
}

function normalizeAgentData(
  raw: Record<string, unknown>,
  agentMap: Map<string, Agent>
): Record<string, unknown> {
  // Already normalized (saved from our canvas)
  if (raw.agentId) return raw;

  const slug = raw.agent as string | undefined;
  if (!slug) return raw;

  const agent =
    agentMap.get(slug) ??
    agentMap.get(slug.toLowerCase()) ??
    agentMap.get(slug.toLowerCase().replace(/_agent$/, ""));

  if (agent) {
    return {
      ...raw,
      agentId: agent.id,
      agentName: agent.name,
      role: agent.role ?? "",
      modelProvider: agent.model_provider,
      modelName: agent.model_name,
      toolsCount: agent.tools_enabled.length,
      label: raw.label ?? agent.name,
    };
  }

  // No exact match — display slug as a human-readable name
  const humanName = slug
    .replace(/_agent$/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

  return {
    ...raw,
    agentName: humanName,
    label: raw.label ?? humanName,
  };
}

function normalizeConditionData(raw: Record<string, unknown>): Record<string, unknown> {
  // Already normalized
  if (raw.operator && raw.value !== undefined) return raw;

  const field = raw.field as string | undefined;
  const cases = raw.cases as Record<string, string> | undefined;
  const threshold = raw.threshold;
  const operator = raw.operator as string | undefined;

  // Has operator + threshold (e.g. reviewer_score >= 7)
  if (operator && threshold !== undefined && !raw.value) {
    return { ...raw, value: String(threshold) };
  }

  // Has cases map (enum routing)
  if (cases) {
    const nonDefault = Object.keys(cases).filter((k) => k !== "default");

    // Boolean cases { "true": "...", "false": "..." }
    if (nonDefault.every((k) => k === "true" || k === "false")) {
      return {
        ...raw,
        field: field ?? "condition",
        operator: operator ?? "eq",
        value: raw.value ?? "true",
      };
    }

    // Enum cases → "in" operator with comma-separated values
    return {
      ...raw,
      field: field ?? "condition",
      operator: "in",
      value: nonDefault.join(", "),
    };
  }

  return raw;
}

export function normalizeNodes(rawNodes: Node[], agents: Agent[]): Node[] {
  const agentMap = buildAgentMap(agents);

  return rawNodes.map((node) => {
    let type = node.type ?? "agent";
    let data = { ...(node.data as Record<string, unknown>) };

    // Map backend type names to our component type names
    if (type === "start") type = "trigger";

    // Per-type data normalization
    switch (type) {
      case "trigger":
        if (!data.channel) data.channel = "telegram";
        break;
      case "agent":
        data = normalizeAgentData(data, agentMap);
        break;
      case "condition":
        data = normalizeConditionData(data);
        break;
      // "end" has no config — nothing to normalize
    }

    return { ...node, type, data };
  });
}
