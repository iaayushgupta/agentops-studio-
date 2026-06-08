"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { type Node, type Edge } from "@xyflow/react";
import { Canvas, transformToReactFlow } from "@/components/workflow-builder/Canvas";
import { getWorkflow, getAgents } from "@/lib/api";
import { normalizeNodes, normalizeEdges } from "@/lib/normalizeWorkflow";
import type { Workflow, Agent } from "@/lib/api";

export default function WorkflowEditorPage() {
  const params = useParams();
  const id = params.id as string;

  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [initialNodes, setInitialNodes] = useState<Node[]>([]);
  const [initialEdges, setInitialEdges] = useState<Edge[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Fetch workflow and agents in parallel — agents needed to resolve slugs → full data
    Promise.all([getWorkflow(id), getAgents()])
      .then(([wf, agents]: [Workflow, Agent[]]) => {
        setWorkflow(wf);

        // transformToReactFlow normalises both DB formats into ReactFlow-compatible
        // nodes/edges before normalizeNodes resolves agent slugs, condition fields, etc.
        //   Format A (Payment Triage):  id/type/data/source/target
        //   Format B (Support/Fraud):   node_id/node_type/config_json/source_node_id/…
        const rf = transformToReactFlow(
          (wf.graph_json ?? {}) as Record<string, unknown>
        );

        setInitialNodes(normalizeNodes(rf.nodes, agents));
        setInitialEdges(normalizeEdges(rf.edges));
      })
      .catch((err) => setError((err as Error).message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
        Loading workflow…
      </div>
    );
  }

  if (error || !workflow) {
    return (
      <div className="flex-1 flex items-center justify-center text-red-500 text-sm">
        {error ?? "Workflow not found."}
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <Canvas
        workflow={workflow}
        initialNodes={initialNodes}
        initialEdges={initialEdges}
      />
    </div>
  );
}
