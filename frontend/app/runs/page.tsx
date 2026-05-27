"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCw } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { getRunsList, getWorkflows } from "@/lib/api";
import type { Run, Workflow } from "@/lib/api";

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

const formatCost = (c: number | null | undefined) => `$${(c ?? 0).toFixed(4)}`;

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const [r, w] = await Promise.all([getRunsList({ limit: 50 }), getWorkflows()]);
      setRuns(r);
      setWorkflows(w);
    } finally { setLoading(false); }
  }

  useEffect(() => {
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, []);

  const workflowMap = workflows.reduce<Record<string, Workflow>>(
    (acc, w) => ({ ...acc, [w.id]: w }),
    {}
  );

  return (
    <>
      <Header
        title="Runs"
        subtitle="All workflow execution history"
        actions={
          <button
            onClick={load}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </button>
        }
      />

      <div className="flex-1 overflow-auto p-6">
        {loading ? (
          <div className="text-center text-slate-400 py-20 text-sm">Loading runs…</div>
        ) : runs.length === 0 ? (
          <div className="text-center text-slate-400 py-20 text-sm">No runs found.</div>
        ) : (
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                  <th className="px-5 py-3 text-left font-medium">Run ID</th>
                  <th className="px-5 py-3 text-left font-medium">Workflow</th>
                  <th className="px-5 py-3 text-left font-medium">Channel</th>
                  <th className="px-5 py-3 text-left font-medium">Status</th>
                  <th className="px-5 py-3 text-left font-medium">Cost</th>
                  <th className="px-5 py-3 text-left font-medium">Duration</th>
                  <th className="px-5 py-3 text-left font-medium">Started</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {runs.map((run) => {
                  const duration =
                    run.started_at && run.ended_at
                      ? `${((new Date(run.ended_at).getTime() - new Date(run.started_at).getTime()) / 1000).toFixed(1)}s`
                      : "—";
                  return (
                    <tr key={run.id} className="hover:bg-slate-50 transition-colors">
                      <td className="px-5 py-3 font-mono text-slate-600">
                        <Link href={`/runs/${run.id}`} className="hover:text-violet-600">
                          {run.id.slice(0, 8)}…
                        </Link>
                      </td>
                      <td className="px-5 py-3 text-slate-600">
                        {run.workflow_id
                          ? (workflowMap[run.workflow_id]?.name ?? run.workflow_id.slice(0, 8) + "…")
                          : "—"}
                      </td>
                      <td className="px-5 py-3 text-slate-600">{run.trigger_channel ?? "—"}</td>
                      <td className="px-5 py-3"><StatusBadge status={run.status} /></td>
                      <td className="px-5 py-3 text-slate-600">
                        {formatCost(run.total_cost_usd)}
                      </td>
                      <td className="px-5 py-3 text-slate-500">{duration}</td>
                      <td className="px-5 py-3 text-slate-500 text-xs">
                        {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
