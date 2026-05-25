"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Plus, Play, Pencil, GitFork, Loader2,
  CreditCard, Headphones,
} from "lucide-react";
import { Header } from "@/components/layout/Header";
import { getWorkflows, getRunsList, triggerRun, createWorkflow } from "@/lib/api";
import type { Workflow, Run } from "@/lib/api";

// ── Helpers ───────────────────────────────────────────────────────────────────

function nodeCount(wf: Workflow): number {
  const gj = wf.graph_json as { nodes?: unknown[] } | null;
  return gj?.nodes?.length ?? 0;
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

// ── Template cards ─────────────────────────────────────────────────────────────

const TEMPLATES = [
  {
    key: "payment_triage",
    name: "Payment Failure Triage",
    description: "Telegram → Intake → Investigator → Condition → Resolution/Escalation → Reviewer → End",
    icon: <CreditCard className="w-5 h-5 text-violet-600" />,
    color: "border-violet-200 bg-gradient-to-br from-violet-50 to-white",
    nodes: 8,
  },
  {
    key: "support_escalation",
    name: "Support Escalation",
    description: "Telegram → Triage → Priority Condition → Tier 1 / Tier 2 → End",
    icon: <Headphones className="w-5 h-5 text-blue-600" />,
    color: "border-blue-200 bg-gradient-to-br from-blue-50 to-white",
    nodes: 6,
  },
];

// ── WorkflowCard ───────────────────────────────────────────────────────────────

interface WorkflowCardProps {
  workflow: Workflow;
  lastRun?: Run;
  onTrigger: (id: string) => void;
  triggering: boolean;
}

function WorkflowCard({ workflow, lastRun, onTrigger, triggering }: WorkflowCardProps) {
  const nc = nodeCount(workflow);
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 flex flex-col gap-3 hover:shadow-sm transition-shadow">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
            <GitFork className="w-4 h-4 text-slate-600" />
          </div>
          <div>
            <p className="font-medium text-slate-900 leading-tight">{workflow.name}</p>
            {workflow.description && (
              <p className="text-xs text-slate-400 mt-0.5 line-clamp-1">{workflow.description}</p>
            )}
          </div>
        </div>
        <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium shrink-0 ${
          workflow.status === "active" ? "bg-emerald-100 text-emerald-700" :
          workflow.status === "draft" ? "bg-amber-100 text-amber-700" :
          "bg-slate-100 text-slate-500"
        }`}>
          {workflow.status}
        </span>
      </div>

      {/* Stats row */}
      <div className="flex items-center gap-3 text-xs text-slate-500">
        <span>{nc} node{nc !== 1 ? "s" : ""}</span>
        {lastRun && (
          <>
            <span>·</span>
            <span>Last run: <StatusBadge status={lastRun.status} /></span>
          </>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-1">
        <Link
          href={`/workflows/${workflow.id}`}
          className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 text-slate-700 text-xs font-medium rounded-lg hover:bg-slate-50 transition-colors"
        >
          <Pencil className="w-3 h-3" />
          Edit
        </Link>
        <button
          onClick={() => onTrigger(workflow.id)}
          disabled={triggering}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 text-white text-xs font-medium rounded-lg hover:bg-violet-700 disabled:opacity-50 transition-colors"
        >
          {triggering ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
          Run
        </button>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function WorkflowsPage() {
  const router = useRouter();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggeringId, setTriggeringId] = useState<string | null>(null);
  const [creatingTemplate, setCreatingTemplate] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getWorkflows(), getRunsList({ limit: 20 })])
      .then(([wfs, rs]) => { setWorkflows(wfs); setRuns(rs); })
      .finally(() => setLoading(false));
  }, []);

  function lastRunFor(wfId: string): Run | undefined {
    return runs.filter((r) => r.workflow_id === wfId).sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    )[0];
  }

  async function handleTrigger(wfId: string) {
    setTriggeringId(wfId);
    try {
      const run = await triggerRun(wfId, { message: "Manual trigger from workflows page" });
      router.push(`/runs/${run.id}`);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setTriggeringId(null);
    }
  }

  async function handleOpenTemplate(key: string) {
    // Try to find existing workflow matching template
    const match = workflows.find((w) =>
      key === "payment_triage"
        ? w.name.toLowerCase().includes("payment") || w.name.toLowerCase().includes("triage")
        : w.name.toLowerCase().includes("support") || w.name.toLowerCase().includes("escalation")
    );
    if (match) {
      router.push(`/workflows/${match.id}`);
      return;
    }
    // Create new workflow and open builder with template pre-loaded
    setCreatingTemplate(key);
    try {
      const wf = await createWorkflow({
        name: key === "payment_triage" ? "Payment Failure Triage" : "Support Escalation",
        status: "draft",
        graph_json: {},
      });
      // Navigate to builder — Canvas will load the template via "Templates" dropdown
      router.push(`/workflows/${wf.id}?template=${key}`);
    } catch {
      router.push("/workflows/new");
    } finally {
      setCreatingTemplate(null);
    }
  }

  return (
    <>
      <Header
        title="Workflows"
        subtitle="Build and manage agent orchestration workflows"
        actions={
          <Link
            href="/workflows/new"
            className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 text-white text-sm font-medium rounded-lg hover:bg-violet-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Workflow
          </Link>
        }
      />

      <div className="flex-1 overflow-auto p-6 space-y-8">

        {/* Template cards */}
        <section>
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">
            Start from a template
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {TEMPLATES.map((tpl) => (
              <div
                key={tpl.key}
                className={`border-2 rounded-xl p-5 flex gap-4 ${tpl.color}`}
              >
                <div className="w-10 h-10 rounded-xl bg-white border border-slate-200 shadow-sm flex items-center justify-center shrink-0">
                  {tpl.icon}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-slate-900">{tpl.name}</p>
                  <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{tpl.description}</p>
                  <p className="text-xs text-slate-400 mt-1">{tpl.nodes} nodes</p>
                  <button
                    onClick={() => handleOpenTemplate(tpl.key)}
                    disabled={creatingTemplate === tpl.key}
                    className="mt-3 flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 text-slate-700 text-xs font-medium rounded-lg hover:bg-slate-50 disabled:opacity-60 transition-colors"
                  >
                    {creatingTemplate === tpl.key
                      ? <Loader2 className="w-3 h-3 animate-spin" />
                      : <Pencil className="w-3 h-3" />
                    }
                    Open in Builder
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Workflow list */}
        <section>
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">
            Your Workflows
          </p>

          {loading ? (
            <div className="text-slate-400 text-sm py-10 text-center">Loading…</div>
          ) : workflows.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-16 text-slate-400">
              <GitFork className="w-10 h-10" />
              <p className="text-sm">No workflows yet.</p>
              <Link href="/workflows/new" className="text-sm text-violet-600 hover:underline">
                Create your first workflow →
              </Link>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
              {workflows.map((wf) => (
                <WorkflowCard
                  key={wf.id}
                  workflow={wf}
                  lastRun={lastRunFor(wf.id)}
                  onTrigger={handleTrigger}
                  triggering={triggeringId === wf.id}
                />
              ))}
            </div>
          )}
        </section>
      </div>
    </>
  );
}
