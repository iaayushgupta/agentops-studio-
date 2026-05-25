"use client";

import { useState } from "react";
import { Send, Loader2 } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { getWorkflows, triggerRun } from "@/lib/api";
import { useRunStream } from "@/lib/websocket";
import type { Workflow } from "@/lib/api";
import { useEffect } from "react";

export default function PlaygroundPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [selectedWorkflow, setSelectedWorkflow] = useState<string>("");
  const [message, setMessage] = useState("TXN-001 payment failed");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { events, status, cost, isConnected, clearEvents } = useRunStream(activeRunId);

  useEffect(() => {
    getWorkflows().then((wfs) => {
      setWorkflows(wfs);
      if (wfs.length > 0) setSelectedWorkflow(wfs[0].id);
    });
  }, []);

  // Clear old run when status reaches terminal state
  useEffect(() => {
    if (status === "completed" || status === "failed") {
      const timer = setTimeout(() => setActiveRunId(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [status]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedWorkflow) { setError("Select a workflow first."); return; }
    setError(null);
    clearEvents();
    setSubmitting(true);
    try {
      const run = await triggerRun(selectedWorkflow, { message });
      setActiveRunId(run.id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  const finalResponse = events.find((e) => e.event_type === "run_completed")?.data?.final_response as string | undefined;

  return (
    <>
      <Header title="Playground" subtitle="Manually trigger workflows and watch them run" />

      <div className="flex-1 overflow-auto p-6 space-y-5 max-w-3xl">

        {/* Trigger form */}
        <form onSubmit={handleSubmit} className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Workflow</label>
            <select
              value={selectedWorkflow}
              onChange={(e) => setSelectedWorkflow(e.target.value)}
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-violet-500"
            >
              {workflows.length === 0 && <option value="">No workflows available</option>}
              {workflows.map((wf) => (
                <option key={wf.id} value={wf.id}>{wf.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Message / Payload</label>
            <textarea
              rows={3}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Describe the input to send to the workflow"
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-violet-500"
            />
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">{error}</p>
          )}

          <button
            type="submit"
            disabled={submitting || !!activeRunId}
            className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white text-sm font-medium rounded-lg hover:bg-violet-700 disabled:opacity-60 transition-colors"
          >
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            {submitting ? "Triggering…" : "Trigger Run"}
          </button>
        </form>

        {/* Live output */}
        {activeRunId && (
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-900">
                  Run <span className="font-mono">{activeRunId.slice(0, 8)}…</span>
                </p>
                <p className="text-xs text-slate-400">
                  Status: <span className="font-medium text-slate-700">{status}</span>
                  {cost > 0 && ` · $${cost.toFixed(4)}`}
                </p>
              </div>
              <span className={`w-2.5 h-2.5 rounded-full ${isConnected ? "bg-emerald-400 animate-pulse" : "bg-slate-300"}`} />
            </div>

            {/* Event feed */}
            <div className="divide-y divide-slate-50 bg-slate-950 max-h-72 overflow-auto flex flex-col-reverse">
              {events.length === 0 ? (
                <div className="px-5 py-4 text-xs text-slate-500">Waiting for events…</div>
              ) : (
                [...events].reverse().map((evt, i) => (
                  <div key={i} className="px-4 py-2 flex items-start gap-3 text-xs font-mono">
                    <span className="text-slate-500 shrink-0">
                      {new Date(evt.timestamp).toLocaleTimeString()}
                    </span>
                    <span className="text-violet-400 shrink-0">{evt.event_type}</span>
                    <span className="text-slate-400 truncate">{JSON.stringify(evt.data)}</span>
                  </div>
                ))
              )}
            </div>

            {/* Final response pill */}
            {finalResponse && (
              <div className="px-5 py-4 bg-emerald-50 border-t border-emerald-200">
                <p className="text-xs font-medium text-emerald-700 mb-1">Final Response</p>
                <p className="text-sm text-emerald-900 leading-relaxed">{finalResponse}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}
