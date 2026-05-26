"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { GitBranch } from "lucide-react";

export interface ConditionNodeData {
  label?: string;
  field?: string;
  operator?: string;
  value?: string;
}

function ConditionNode({ data, selected }: NodeProps) {
  const d = data as ConditionNodeData;

  const opLabel: Record<string, string> = {
    eq: "==", neq: "!=", gt: ">", gte: ">=", lt: "<", lte: "<=", in: "in",
  };

  const summary = d.field
    ? `${d.field} ${opLabel[d.operator ?? "eq"] ?? d.operator} ${d.value ?? "?"}`
    : "Configure condition";

  return (
    <div className="relative flex items-center justify-center" style={{ width: 160, height: 100 }}>
      {/* Diamond shape via rotated square */}
      <div
        className={`absolute inset-0 m-auto rounded-lg border-2 bg-amber-50 shadow-sm transition-all ${
          selected
            ? "border-amber-500 shadow-amber-200 shadow-md"
            : "border-amber-300"
        }`}
        style={{
          width: 112,
          height: 112,
          transform: "rotate(45deg)",
          top: -6,
          left: 24,
          position: "absolute",
        }}
      />

      {/* Content (un-rotated) */}
      <div className="relative z-10 flex flex-col items-center gap-1 px-2 text-center">
        <div className="w-6 h-6 rounded-full bg-amber-500 flex items-center justify-center">
          <GitBranch className="w-3.5 h-3.5 text-white" />
        </div>
        <span className="text-[9px] font-semibold text-amber-800 leading-tight max-w-[120px] truncate">
          {summary}
        </span>
      </div>

      {/* Incoming handle — left */}
      <Handle
        type="target"
        position={Position.Left}
        className="!w-3 !h-3 !bg-amber-400 !border-2 !border-white"
        style={{ left: 4 }}
      />

      {/* True handle — right-top, green */}
      <Handle
        type="source"
        position={Position.Right}
        id="true"
        className="!w-3 !h-3 !bg-emerald-500 !border-2 !border-white"
        style={{ top: "30%", right: 4 }}
      />
      {/* False handle — right-bottom, red */}
      <Handle
        type="source"
        position={Position.Right}
        id="false"
        className="!w-3 !h-3 !bg-red-500 !border-2 !border-white"
        style={{ top: "70%", right: 4 }}
      />

      {/* True / False labels */}
      <span
        className="absolute text-[8px] font-bold text-emerald-600 pointer-events-none"
        style={{ right: -28, top: "22%" }}
      >
        true
      </span>
      <span
        className="absolute text-[8px] font-bold text-red-500 pointer-events-none"
        style={{ right: -30, top: "62%" }}
      >
        false
      </span>
    </div>
  );
}

export default memo(ConditionNode);
