"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Send, MousePointerClick } from "lucide-react";

export interface TriggerNodeData {
  label: string;
  channel?: "telegram" | "manual";
}

function TriggerNode({ data, selected }: NodeProps) {
  const d = data as TriggerNodeData;
  const isTelegram = (d.channel ?? "telegram") === "telegram";

  return (
    <div
      className={`min-w-[140px] rounded-2xl border-2 bg-white shadow-sm transition-all ${
        selected
          ? "border-blue-500 shadow-blue-200 shadow-md"
          : "border-blue-200"
      }`}
    >
      <div className="flex items-center gap-2 px-3 py-2.5 bg-blue-50 rounded-2xl">
        <div className="w-7 h-7 rounded-xl bg-blue-600 flex items-center justify-center shrink-0">
          {isTelegram ? (
            <Send className="w-3.5 h-3.5 text-white" />
          ) : (
            <MousePointerClick className="w-3.5 h-3.5 text-white" />
          )}
        </div>
        <div>
          <p className="text-[10px] font-bold text-blue-900 uppercase tracking-wide">
            Trigger
          </p>
          <p className="text-xs font-medium text-blue-700">
            {isTelegram ? "Telegram" : "Manual"}
          </p>
        </div>
      </div>

      {/* Only a source handle — nothing routes into a trigger */}
      <Handle
        type="source"
        position={Position.Right}
        className="!w-3 !h-3 !bg-blue-400 !border-2 !border-white"
      />
    </div>
  );
}

export default memo(TriggerNode);
