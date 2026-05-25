"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { CheckCircle } from "lucide-react";

export interface EndNodeData {
  label: string;
}

function EndNode({ selected }: NodeProps) {
  return (
    <div
      className={`min-w-[120px] rounded-xl border-2 bg-white shadow-sm transition-all ${
        selected
          ? "border-emerald-500 shadow-emerald-200 shadow-md"
          : "border-emerald-200"
      }`}
    >
      <div className="flex items-center gap-2 px-3 py-2.5 bg-emerald-50 rounded-xl">
        <div className="w-7 h-7 rounded-xl bg-emerald-600 flex items-center justify-center shrink-0">
          <CheckCircle className="w-3.5 h-3.5 text-white" />
        </div>
        <div>
          <p className="text-[10px] font-bold text-emerald-900 uppercase tracking-wide">
            End
          </p>
          <p className="text-[10px] text-emerald-700">Workflow complete</p>
        </div>
      </div>

      {/* Only a target handle — nothing routes out of an end node */}
      <Handle
        type="target"
        position={Position.Left}
        className="!w-3 !h-3 !bg-emerald-400 !border-2 !border-white"
      />
    </div>
  );
}

export default memo(EndNode);
