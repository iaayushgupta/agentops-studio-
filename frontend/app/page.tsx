"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bot, GitFork, PlayCircle, DollarSign, Plus, RefreshCw } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { getAgents, getWorkflows, getRunsList, getRunTimeline } from "@/lib/api";
import type { Agent, Workflow, Run } from "@/lib/api";

// ── Stat card ─────────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  color: string;
}

function StatCard({ label, value, icon, color }: StatCardProps) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 flex items-center gap-4">
      <div className={`w-11 h-11 rounded-lg flex items-center justify-center ${color}`}>
        {icon}
      </div>
      <div>
        <p className="text-sm text-slate-500">{label}</p>
        <p className="text-2xl font-semibold text-slate-900">{value}</p>
      </div>
    </div>
  );
}

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    completed: "bg-emerald-100 text-emerald-700",
    running:   "bg-blue-100 text-blue-700",
    pending:   "bg-amber-100 text-amber-700",
    failed:    "bg-red-100 text-red-700",
    cancelled: "bg-slate-100 text-slate-600",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${map[status] ?? "bg-slate-100 text-slate-600"}`}>
      {status}
    </span>
  );
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [totalCost, setTotalCost] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setTotalCost(null);
    try {
      const [a, w, r] = await Promise.all([
        getAgents(),
        getWorkflows(),
        getRunsList({ limit: 10 }),
      ]);
      setAgents(a);
      setWorkflows(w);
      setRuns(r);

      // GET /runs does NOT return total_cost_usd — it's only in the timeline's
      // embedded run object. Fetch timelines for completed runs in parallel to
      // get the real costs, then sum them.
      const completedIds = r
        .filter((run) => run.status === "completed")
        .map((run) => run.id);

      if (completedIds.length > 0) {
        const timelines = await Promise.all(
          completedIds.map((id) => getRunTimeline(id).catch(() => null))
        );
        const sum = timelines.reduce(
          (acc, t) => acc + (t?.run?.total_cost_usd ?? 0),
          0
        );
        setTotalCost(sum);
      } else {
        setTotalCost(0);
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const completedRuns = runs.filter((r) => r.status === "completed").length;

  const workflowMap = workflows.reduce<Record<string, Workflow>>(
    (acc, w) => ({ ...acc, [w.id]: w }),
    {}
  );

  const formatCost = (c: number | null | undefined) => `$${(c ?? 0).toFixed(4)}`;

  return (
    <>
      <Header
        title="Dashboard"
        subtitle="AgentOps Studio overview"
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

      <div className="flex-1 overflow-auto p-6 space-y-6">
        {/* Stat cards */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          <StatCard
            label="Total Agents"
            value={loading ? "—" : agents.length}
            icon={<Bot className="w-5 h-5 text-violet-600" />}
            color="bg-violet-50"
          />
          <StatCard
            label="Workflows"
            value={loading ? "—" : workflows.length}
            icon={<GitFork className="w-5 h-5 text-blue-600" />}
            color="bg-blue-50"
          />
          <StatCard
            label="Completed Runs"
            value={loading ? "—" : completedRuns}
            icon={<PlayCircle className="w-5 h-5 text-emerald-600" />}
            color="bg-emerald-50"
          />
          <StatCard
            label="Total Cost (USD)"
            value={
              loading || totalCost === null
                ? "—"
                : `$${totalCost.toFixed(4)}`
            }
            icon={<DollarSign className="w-5 h-5 text-amber-600" />}
            color="bg-amber-50"
          />
        </div>

        {/* Quick links */}
        <div className="flex gap-3">
          <Link
            href="/agents/new"
            className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 text-white text-sm font-medium rounded-lg hover:bg-violet-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Agent
          </Link>
          <Link
            href="/workflows/new"
            className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Workflow
          </Link>
        </div>

        {/* Recent Runs table */}
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
            <h2 className="font-medium text-slate-900">Recent Runs</h2>
            <Link href="/runs" className="text-sm text-violet-600 hover:underline">
              View all
            </Link>
          </div>

          {loading ? (
            <div className="px-5 py-10 text-center text-slate-400 text-sm">Loading…</div>
          ) : runs.length === 0 ? (
            <div className="px-5 py-10 text-center text-slate-400 text-sm">
              No runs yet. Trigger a workflow to get started.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                  <th className="px-5 py-3 text-left font-medium">Run ID</th>
                  <th className="px-5 py-3 text-left font-medium">Workflow</th>
                  <th className="px-5 py-3 text-left font-medium">Channel</th>
                  <th className="px-5 py-3 text-left font-medium">Status</th>
                  <th className="px-5 py-3 text-left font-medium">Cost</th>
                  <th className="px-5 py-3 text-left font-medium">Started</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {runs.map((run) => (
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
                    <td className="px-5 py-3 text-slate-600">
                      {run.trigger_channel ?? "—"}
                    </td>
                    <td className="px-5 py-3">
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="px-5 py-3 text-slate-600">
                      {formatCost(run.total_cost_usd)}
                    </td>
                    <td className="px-5 py-3 text-slate-500">
                      {run.started_at
                        ? new Date(run.started_at).toLocaleString()
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  );
}
