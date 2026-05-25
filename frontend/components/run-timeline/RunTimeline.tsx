"use client";

/**
 * RunTimeline — visual step-by-step breakdown of a completed run.
 *
 * TODO: full implementation
 *  - Vertical timeline with step cards
 *  - Tool call sub-entries per step
 *  - Token usage bar per step
 *  - Collapsible message thread per step
 */

import type { RunTimeline as RunTimelineData } from "@/lib/api";

interface RunTimelineProps {
  timeline: RunTimelineData;
}

export function RunTimeline({ timeline }: RunTimelineProps) {
  return (
    <div className="space-y-3">
      {timeline.steps.map((step, i) => (
        <div key={step.id} className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-medium text-slate-500">Step {i + 1}</span>
            <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
              step.status === "completed" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"
            }`}>
              {step.status}
            </span>
          </div>
          {step.output && (
            <pre className="text-xs text-slate-600 bg-slate-50 rounded p-2 overflow-auto max-h-32 whitespace-pre-wrap">
              {JSON.stringify(step.output, null, 2)}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}
