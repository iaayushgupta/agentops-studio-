"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Bot } from "lucide-react";

export interface AgentNodeData {
  label?: string;
  agentId?: string;
  agentName?: string;
  /** Canonical role field (set by normalizer or config panel) */
  role?: string;
  /** Alternative role field key used by some backend payloads */
  agent_role?: string;
  modelProvider?: string;
  modelName?: string;
  /** Number of tools the agent has enabled — set by normalizeNodes */
  toolsCount?: number;
  selected?: boolean;
}

function AgentNode({ data, selected }: NodeProps) {
  const d = data as AgentNodeData;
  return (
    <div
      className={`min-w-[160px] rounded-xl border-2 bg-white shadow-sm transition-all ${
        selected
          ? "border-violet-500 shadow-violet-200 shadow-md"
          : "border-violet-200"
      }`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 bg-violet-50 rounded-t-xl border-b border-violet-100">
        <div className="w-6 h-6 rounded-md bg-violet-600 flex items-center justify-center shrink-0">
          <Bot className="w-3.5 h-3.5 text-white" />
        </div>
        <span className="text-xs font-semibold text-violet-900 truncate max-w-[110px]">
          {d.agentName ?? d.label ?? "Agent"}
        </span>
      </div>

      {/* Body */}
      <div className="px-3 py-2 flex flex-wrap gap-1">
        {/* Role badge — check both 'role' and 'agent_role' keys */}
        {(d.role || d.agent_role) && (
          <span className="inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium bg-violet-100 text-violet-700">
            {d.role || d.agent_role}
          </span>
        )}
        {/* Model badge */}
        {d.modelName && (
          <span className="inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-600">
            {d.modelName}
          </span>
        )}
        {/* Tools count badge */}
        {typeof d.toolsCount === "number" && d.toolsCount > 0 && (
          <span className="inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-100 text-blue-700">
            {d.toolsCount} tools
          </span>
        )}
        {/* Fallback — nothing configured yet */}
        {!d.role && !d.agent_role && !d.modelName && (
          <span className="text-[10px] text-slate-400 italic">Select agent</span>
        )}
      </div>

      <Handle
        type="target"
        position={Position.Left}
        className="!w-3 !h-3 !bg-violet-400 !border-2 !border-white"
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!w-3 !h-3 !bg-violet-400 !border-2 !border-white"
      />
    </div>
  );
}

export default memo(AgentNode);
