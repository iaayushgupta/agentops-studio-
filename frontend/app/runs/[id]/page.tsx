"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { CheckCircle, XCircle, Loader2, Clock, DollarSign, Zap } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { getRun, getRunTimeline, cancelRun, getAgents } from "@/lib/api";
import { useRunStream } from "@/lib/websocket";
import type { Run, RunTimeline, Agent } from "@/lib/api";

// ── Status helpers ────────────────────────────────────────────────────────────

function StatusIcon({ status }: { status: string }) {
  if (status === "completed") return <CheckCircle className="w-4 h-4 text-emerald-500" />;
  if (status === "failed") return <XCircle className="w-4 h-4 text-red-500" />;
  if (status === "running" || status === "pending") return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />;
  return <Clock className="w-4 h-4 text-slate-400" />;
}

// Role badge — colour-coded by agent role
const ROLE_COLORS: Record<string, string> = {
  intake:       "bg-blue-100 text-blue-700",
  investigator: "bg-purple-100 text-purple-700",
  resolver:     "bg-emerald-100 text-emerald-700",
  reviewer:     "bg-amber-100 text-amber-700",
  escalator:    "bg-red-100 text-red-700",
  escalation:   "bg-red-100 text-red-700",
};

function RoleBadge({ role }: { role: string | null | undefined }) {
  if (!role) return null;
  return (
    <span className={`inline-flex px-1.5 py-0.5 rounded text-[10px] font-medium ${ROLE_COLORS[role] ?? "bg-slate-100 text-slate-600"}`}>
      {role}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed: "bg-emerald-100 text-emerald-700",
    running:   "bg-blue-100 text-blue-700",
    pending:   "bg-amber-100 text-amber-700",
    failed:    "bg-red-100 text-red-700",
    cancelled: "bg-slate-100 text-slate-600",
  };
  return (
    <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${map[status] ?? "bg-slate-100 text-slate-600"}`}>
      {status}
    </span>
  );
}

// ── Run detail ────────────────────────────────────────────────────────────────

export default function RunDetailPage() {
  const params = useParams();
  const runId = params.id as string;

  const [run, setRun] = useState<Run | null>(null);
  const [timeline, setTimeline] = useState<RunTimeline | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [cancelling, setCancelling] = useState(false);

  // Live stream while run is active
  const isActive = run?.status === "running" || run?.status === "pending";
  const { events, status: wsStatus, cost: wsCost, isConnected } = useRunStream(
    isActive ? runId : null
  );

  // Load initial state
  useEffect(() => {
    Promise.all([getRun(runId), getRunTimeline(runId), getAgents()])
      .then(([r, t, a]) => { setRun(r); setTimeline(t); setAgents(a); })
      .finally(() => setLoading(false));
  }, [runId]);

  // Re-fetch timeline when run completes via WebSocket
  useEffect(() => {
    if (wsStatus === "completed" || wsStatus === "failed") {
      Promise.all([getRun(runId), getRunTimeline(runId)]).then(([r, t]) => {
        setRun(r);
        setTimeline(t);
      });
    }
  }, [wsStatus, runId]);

  async function handleCancel() {
    if (!confirm("Cancel this run?")) return;
    setCancelling(true);
    try {
      const updated = await cancelRun(runId);
      setRun(updated);
    } finally {
      setCancelling(false);
    }
  }

  if (loading) return <div className="p-10 text-slate-400 text-sm">Loading run…</div>;
  if (!run) return <div className="p-10 text-red-500 text-sm">Run not found.</div>;

  const effectiveStatus = (wsStatus !== "idle" && isActive) ? wsStatus : run.status;
  // total_cost_usd is only present on the timeline's embedded run object,
  // not on the shallow GET /runs/{id} response. Prefer timeline, fall back
  // to the live WebSocket cost for in-progress runs.
  const effectiveCost = wsCost || timeline?.run?.total_cost_usd || 0;

  // Agent lookup: two maps so step.agent_id works whether it's a UUID or a name string
  const agentById = agents.reduce<Record<string, Agent>>(
    (acc, a) => ({ ...acc, [a.id]: a }),
    {}
  );
  const agentByName = agents.reduce<Record<string, Agent>>(
    (acc, a) => ({ ...acc, [a.name]: a }),
    {}
  );
  console.log("agentMap keys:", Object.keys(agentById));
  console.log("first step agent_id:", timeline?.steps[0]?.agent_id);

  // Replace agent_id in event data with resolved name for readability
  function resolveEventData(evtData: Record<string, unknown>): Record<string, unknown> {
    if (!evtData || typeof evtData !== "object") return evtData;
    const out = { ...evtData };
    if (typeof out.agent_id === "string") {
      const resolved = agentById[out.agent_id] || agentByName[out.agent_id];
      if (resolved) out.agent_id = resolved.name;
    }
    return out;
  }

  return (
    <>
      <Header
        title={`Run ${run.id.slice(0, 8)}…`}
        subtitle={run.trigger_channel ? `Triggered via ${run.trigger_channel}` : "Manual trigger"}
        actions={
          (run.status === "running" || run.status === "pending") && (
            <button
              onClick={handleCancel}
              disabled={cancelling}
              className="px-3 py-1.5 text-sm text-red-600 border border-red-200 rounded-lg hover:bg-red-50 disabled:opacity-60 transition-colors"
            >
              {cancelling ? "Cancelling…" : "Cancel Run"}
            </button>
          )
        }
      />

      <div className="flex-1 overflow-auto p-6 space-y-5">

        {/* Meta cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-white border border-slate-200 rounded-xl p-4 flex items-center gap-3">
            <StatusIcon status={effectiveStatus} />
            <div>
              <p className="text-xs text-slate-500">Status</p>
              <StatusBadge status={effectiveStatus} />
            </div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-4 flex items-center gap-3">
            <DollarSign className="w-4 h-4 text-amber-500" />
            <div>
              <p className="text-xs text-slate-500">Cost</p>
              <p className="text-sm font-semibold text-slate-900">${effectiveCost.toFixed(4)}</p>
            </div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-4 flex items-center gap-3">
            <Zap className="w-4 h-4 text-violet-500" />
            <div>
              <p className="text-xs text-slate-500">Tokens</p>
              <p className="text-sm font-semibold text-slate-900">
                {timeline?.token_usage?.total_tokens?.toLocaleString() ?? "—"}
              </p>
            </div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-4 flex items-center gap-3">
            <Clock className="w-4 h-4 text-slate-400" />
            <div>
              <p className="text-xs text-slate-500">Started</p>
              <p className="text-sm text-slate-700">
                {run.started_at ? new Date(run.started_at).toLocaleTimeString() : "—"}
              </p>
            </div>
          </div>
        </div>

        {/* Final Response — only available via timeline.run, not GET /runs/{id} */}
        {(timeline?.run?.final_response) && (
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-5">
            <p className="text-xs font-medium text-emerald-700 mb-1">Final Response</p>
            <p className="text-sm text-emerald-900 leading-relaxed">{timeline.run.final_response}</p>
          </div>
        )}

        {/* Error — only available via timeline.run */}
        {(timeline?.run?.error_message) && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-5">
            <p className="text-xs font-medium text-red-700 mb-1">Error</p>
            <p className="text-sm text-red-800 font-mono">{timeline.run.error_message}</p>
          </div>
        )}

        {/* Live Event Stream */}
        {isActive && (
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between">
              <h2 className="font-medium text-slate-900 text-sm">Live Events</h2>
              <span className={`w-2 h-2 rounded-full ${isConnected ? "bg-emerald-400 animate-pulse" : "bg-slate-300"}`} />
            </div>
            <div className="divide-y divide-slate-50 max-h-60 overflow-auto">
              {events.length === 0 ? (
                <div className="px-5 py-4 text-xs text-slate-400">Waiting for events…</div>
              ) : (
                [...events].reverse().map((evt, i) => (
                  <div key={i} className="px-5 py-2.5 flex items-start gap-3 text-xs">
                    <span className="font-mono text-slate-400 shrink-0 pt-px">
                      {new Date(evt.timestamp).toLocaleTimeString()}
                    </span>
                    <span className="text-violet-700 font-medium shrink-0">{evt.event_type}</span>
                    <span className="text-slate-500 truncate">
                      {JSON.stringify(resolveEventData(evt.data as Record<string, unknown>))}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* Steps timeline */}
        {timeline && timeline.steps.length > 0 && (
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <div className="px-5 py-3 border-b border-slate-100">
              <h2 className="font-medium text-slate-900 text-sm">Steps</h2>
            </div>
            <div className="divide-y divide-slate-100">
              {timeline.steps.map((step, i) => {
                const agent =
                  agentById[step.agent_id ?? ""] ||
                  agentByName[step.agent_id ?? ""] ||
                  null;
                return (
                  <div key={step.id} className="px-5 py-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs text-slate-400 font-mono w-5 shrink-0">{i + 1}</span>
                      <StatusBadge status={step.status} />
                      {agent ? (
                        <>
                          <span className="text-xs font-medium text-slate-800">{agent.name}</span>
                          <RoleBadge role={agent.role} />
                        </>
                      ) : (
                        <span className="text-xs text-slate-400">
                          {step.agent_id?.slice(0, 8) || "unknown"}
                        </span>
                      )}
                    </div>
                    {step.output && (
                      <pre className="mt-1 ml-7 text-xs text-slate-600 bg-slate-50 rounded p-2 overflow-auto max-h-28 whitespace-pre-wrap">
                        {JSON.stringify(step.output, null, 2)}
                      </pre>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Messages */}
        {timeline && timeline.messages.length > 0 && (
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <div className="px-5 py-3 border-b border-slate-100">
              <h2 className="font-medium text-slate-900 text-sm">Messages</h2>
            </div>
            <div className="divide-y divide-slate-100 max-h-80 overflow-auto">
              {timeline.messages.map((msg) => (
                <div key={msg.id} className="px-5 py-3">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs font-medium ${
                      msg.role === "user" ? "text-blue-600" :
                      msg.role === "assistant" ? "text-violet-600" :
                      msg.role === "tool" ? "text-amber-600" : "text-slate-500"
                    }`}>{msg.role}</span>
                    <span className="text-xs text-slate-400">
                      {new Date(msg.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="text-xs text-slate-700 leading-relaxed whitespace-pre-wrap line-clamp-4">
                    {msg.content}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
