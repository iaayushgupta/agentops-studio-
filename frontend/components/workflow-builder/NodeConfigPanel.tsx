"use client";

import { useEffect, useState } from "react";
import { type Node } from "@xyflow/react";
import { Settings, Bot, GitBranch, Send, CheckCircle } from "lucide-react";
import { getAgents } from "@/lib/api";
import type { Agent } from "@/lib/api";

interface NodeConfigPanelProps {
  node: Node | null;
  onChange: (nodeId: string, data: Record<string, unknown>) => void;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="block text-xs font-medium text-slate-600">{label}</label>
      {children}
    </div>
  );
}

function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-transparent bg-white"
    />
  );
}

function Select(props: React.SelectHTMLAttributes<HTMLSelectElement> & { children: React.ReactNode }) {
  return (
    <select
      {...props}
      className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-violet-400 focus:border-transparent"
    />
  );
}

// ── Panel sections per node type ─────────────────────────────────────────────

function AgentConfig({ data, onChange }: { data: Record<string, unknown>; onChange: (d: Record<string, unknown>) => void }) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(true);

  useEffect(() => {
    getAgents()
      .then(setAgents)
      .catch(() => {})
      .finally(() => setLoadingAgents(false));
  }, []);

  // selectedAgent may come from the fetched list, or we synthesize from normalized data
  const selectedAgent = agents.find((a) => a.id === (data.agentId as string));

  // Display info: prefer live agent data, fall back to normalized fields already in data
  const displayRole     = selectedAgent?.role ?? (data.role as string | undefined);
  const displayProvider = selectedAgent?.model_provider ?? (data.modelProvider as string | undefined);
  const displayModel    = selectedAgent?.model_name ?? (data.modelName as string | undefined);
  const displayTools    = selectedAgent?.tools_enabled.length ?? undefined;
  const displayTemp     = selectedAgent?.temperature ?? undefined;

  function handleAgentChange(id: string) {
    const agent = agents.find((a) => a.id === id);
    onChange({
      ...data,
      agentId: id,
      agentName: agent?.name ?? "",
      role: agent?.role ?? "",
      modelProvider: agent?.model_provider ?? "",
      modelName: agent?.model_name ?? "",
      label: agent?.name ?? data.label,
    });
  }

  const hasPreview = displayRole || displayProvider || displayModel;

  return (
    <div className="space-y-3">
      <Field label="Agent">
        {loadingAgents ? (
          // While agents are loading, show the pre-normalized name as read-only
          <div className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-sm bg-slate-50 text-slate-500">
            {(data.agentName as string) || "Loading agents…"}
          </div>
        ) : (
          <Select
            value={(data.agentId as string) ?? ""}
            onChange={(e) => handleAgentChange(e.target.value)}
          >
            <option value="">— select agent —</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </Select>
        )}
      </Field>

      {/* Show resolved badges from either live agent data or normalized data prop */}
      {hasPreview && (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {displayRole && (
            <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-violet-100 text-violet-700">
              {displayRole}
            </span>
          )}
          {displayProvider && displayModel && (
            <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-600">
              {displayProvider}/{displayModel}
            </span>
          )}
          {displayTemp !== undefined && (
            <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-600">
              temp {displayTemp}
            </span>
          )}
          {displayTools !== undefined && displayTools > 0 && (
            <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-blue-100 text-blue-700">
              {displayTools} tools
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function ConditionConfig({ data, onChange }: { data: Record<string, unknown>; onChange: (d: Record<string, unknown>) => void }) {
  const operators = ["eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in"];
  const opLabels: Record<string, string> = {
    eq: "== (equals)", neq: "!= (not equals)", gt: "> (greater than)",
    gte: ">= (greater or equal)", lt: "< (less than)", lte: "<= (less or equal)",
    in: "in (list contains)", not_in: "not in",
  };

  return (
    <div className="space-y-3">
      <Field label="Field name">
        <Input
          value={(data.field as string) ?? ""}
          onChange={(e) => onChange({ ...data, field: e.target.value })}
          placeholder="e.g. failure_type"
        />
      </Field>
      <Field label="Operator">
        <Select
          value={(data.operator as string) ?? "eq"}
          onChange={(e) => onChange({ ...data, operator: e.target.value })}
        >
          {operators.map((op) => (
            <option key={op} value={op}>{opLabels[op]}</option>
          ))}
        </Select>
      </Field>
      <Field label="Value">
        <Input
          value={(data.value as string) ?? ""}
          onChange={(e) => onChange({ ...data, value: e.target.value })}
          placeholder="e.g. gateway_error"
        />
      </Field>
      <p className="text-[10px] text-slate-400 leading-relaxed">
        Connect the <span className="text-emerald-600 font-medium">true</span> handle for the matching branch,{" "}
        <span className="text-red-500 font-medium">false</span> for the fallback.
      </p>
    </div>
  );
}

function TriggerConfig({ data, onChange }: { data: Record<string, unknown>; onChange: (d: Record<string, unknown>) => void }) {
  return (
    <div className="space-y-3">
      <Field label="Channel">
        <Select
          value={(data.channel as string) ?? "telegram"}
          onChange={(e) => onChange({ ...data, channel: e.target.value, label: e.target.value === "telegram" ? "Telegram" : "Manual" })}
        >
          <option value="telegram">Telegram</option>
          <option value="manual">Manual</option>
        </Select>
      </Field>
      <p className="text-[10px] text-slate-400">
        The trigger node is always the entry point. Only one trigger per workflow.
      </p>
    </div>
  );
}

function EndConfig() {
  return (
    <div className="space-y-2">
      <p className="text-xs text-slate-500 leading-relaxed">
        The End node marks workflow completion. The final agent's{" "}
        <code className="text-[10px] bg-slate-100 px-1 py-0.5 rounded">customer_message</code> field is sent as the response.
      </p>
      <p className="text-[10px] text-slate-400">No configuration required.</p>
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

const TYPE_ICONS: Record<string, React.ReactNode> = {
  agent:     <Bot className="w-4 h-4 text-violet-600" />,
  condition: <GitBranch className="w-4 h-4 text-amber-600" />,
  trigger:   <Send className="w-4 h-4 text-blue-600" />,
  end:       <CheckCircle className="w-4 h-4 text-emerald-600" />,
};

const TYPE_LABELS: Record<string, string> = {
  agent: "Agent Node", condition: "Condition Node", trigger: "Trigger Node", end: "End Node",
};

export function NodeConfigPanel({ node, onChange }: NodeConfigPanelProps) {
  if (!node) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2 text-slate-400 px-4">
        <Settings className="w-8 h-8" />
        <p className="text-sm text-center">Select a node to configure</p>
      </div>
    );
  }

  const data = node.data as Record<string, unknown>;
  const nodeType = node.type ?? "agent";

  function handleChange(newData: Record<string, unknown>) {
    onChange(node.id, newData);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-100">
        {TYPE_ICONS[nodeType]}
        <div>
          <p className="text-xs font-semibold text-slate-800">{TYPE_LABELS[nodeType] ?? nodeType}</p>
          <p className="text-[10px] text-slate-400 font-mono">{node.id}</p>
        </div>
      </div>

      {/* Config body */}
      <div className="flex-1 overflow-auto px-4 py-4">
        {nodeType === "agent" && <AgentConfig data={data} onChange={handleChange} />}
        {nodeType === "condition" && <ConditionConfig data={data} onChange={handleChange} />}
        {nodeType === "trigger" && <TriggerConfig data={data} onChange={handleChange} />}
        {nodeType === "end" && <EndConfig />}
      </div>
    </div>
  );
}
