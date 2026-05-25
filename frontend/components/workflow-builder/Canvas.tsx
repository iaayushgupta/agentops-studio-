"use client";

import {
  useCallback, useRef, useState, useEffect, type DragEvent,
} from "react";
import { useRouter } from "next/navigation";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  BackgroundVariant,
  type Node,
  type Edge,
  type Connection,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import {
  Save, Play, ChevronDown, ChevronUp,
  Bot, GitBranch, Send, CheckCircle, Loader2,
} from "lucide-react";

import AgentNode from "./nodes/AgentNode";
import ConditionNode from "./nodes/ConditionNode";
import TriggerNode from "./nodes/TriggerNode";
import EndNode from "./nodes/EndNode";
import { NodeConfigPanel } from "./NodeConfigPanel";
import { createWorkflow, updateWorkflow, triggerRun, getWorkflows } from "@/lib/api";
import { useRunStream } from "@/lib/websocket";
import type { Workflow } from "@/lib/api";

// ── Node types registration ───────────────────────────────────────────────────

const NODE_TYPES = {
  agent:     AgentNode,
  condition: ConditionNode,
  trigger:   TriggerNode,
  end:       EndNode,
};

// ── Palette item definitions ─────────────────────────────────────────────────

const PALETTE_ITEMS = [
  {
    type: "trigger",
    label: "Trigger",
    icon: <Send className="w-4 h-4 text-blue-600" />,
    color: "border-blue-200 bg-blue-50",
    defaultData: { label: "Telegram", channel: "telegram" },
  },
  {
    type: "agent",
    label: "Agent",
    icon: <Bot className="w-4 h-4 text-violet-600" />,
    color: "border-violet-200 bg-violet-50",
    defaultData: { label: "Agent" },
  },
  {
    type: "condition",
    label: "Condition",
    icon: <GitBranch className="w-4 h-4 text-amber-600" />,
    color: "border-amber-200 bg-amber-50",
    defaultData: { label: "Condition", operator: "eq" },
  },
  {
    type: "end",
    label: "End",
    icon: <CheckCircle className="w-4 h-4 text-emerald-600" />,
    color: "border-emerald-200 bg-emerald-50",
    defaultData: { label: "End" },
  },
];

// ── Payment Triage template ───────────────────────────────────────────────────

const PAYMENT_TRIAGE_TEMPLATE: { nodes: Node[]; edges: Edge[] } = {
  nodes: [
    { id: "trigger-1", type: "trigger", position: { x: 40, y: 200 }, data: { label: "Telegram", channel: "telegram" } },
    { id: "agent-intake", type: "agent", position: { x: 240, y: 180 }, data: { label: "Intake Agent", agentName: "Intake Agent", role: "intake" } },
    { id: "agent-investigator", type: "agent", position: { x: 460, y: 180 }, data: { label: "Investigator Agent", agentName: "Investigator Agent", role: "investigator" } },
    { id: "condition-failure", type: "condition", position: { x: 680, y: 180 }, data: { label: "failure_type", field: "failure_type", operator: "eq", value: "gateway_error" } },
    { id: "agent-resolution", type: "agent", position: { x: 900, y: 80 }, data: { label: "Resolution Agent", agentName: "Resolution Agent", role: "resolution" } },
    { id: "agent-escalation", type: "agent", position: { x: 900, y: 300 }, data: { label: "Escalation Agent", agentName: "Escalation Agent", role: "escalation" } },
    { id: "agent-reviewer", type: "agent", position: { x: 1120, y: 180 }, data: { label: "Reviewer Agent", agentName: "Reviewer Agent", role: "reviewer" } },
    { id: "end-1", type: "end", position: { x: 1340, y: 180 }, data: { label: "End" } },
  ],
  edges: [
    { id: "e1", source: "trigger-1", target: "agent-intake" },
    { id: "e2", source: "agent-intake", target: "agent-investigator" },
    { id: "e3", source: "agent-investigator", target: "condition-failure" },
    { id: "e4", source: "condition-failure", sourceHandle: "true", target: "agent-resolution" },
    { id: "e5", source: "condition-failure", sourceHandle: "false", target: "agent-escalation" },
    { id: "e6", source: "agent-resolution", target: "agent-reviewer" },
    { id: "e7", source: "agent-escalation", target: "agent-reviewer" },
    { id: "e8", source: "agent-reviewer", target: "end-1" },
  ],
};

const SUPPORT_ESCALATION_TEMPLATE: { nodes: Node[]; edges: Edge[] } = {
  nodes: [
    { id: "trigger-1", type: "trigger", position: { x: 40, y: 160 }, data: { label: "Telegram", channel: "telegram" } },
    { id: "agent-triage", type: "agent", position: { x: 240, y: 140 }, data: { label: "Triage Agent", agentName: "Triage Agent", role: "triage" } },
    { id: "condition-priority", type: "condition", position: { x: 460, y: 140 }, data: { label: "priority", field: "priority", operator: "eq", value: "high" } },
    { id: "agent-tier2", type: "agent", position: { x: 680, y: 60 }, data: { label: "Tier 2 Agent", agentName: "Tier 2 Agent", role: "tier2" } },
    { id: "agent-tier1", type: "agent", position: { x: 680, y: 240 }, data: { label: "Tier 1 Agent", agentName: "Tier 1 Agent", role: "tier1" } },
    { id: "end-1", type: "end", position: { x: 900, y: 140 }, data: { label: "End" } },
  ],
  edges: [
    { id: "e1", source: "trigger-1", target: "agent-triage" },
    { id: "e2", source: "agent-triage", target: "condition-priority" },
    { id: "e3", source: "condition-priority", sourceHandle: "true", target: "agent-tier2" },
    { id: "e4", source: "condition-priority", sourceHandle: "false", target: "agent-tier1" },
    { id: "e5", source: "agent-tier2", target: "end-1" },
    { id: "e6", source: "agent-tier1", target: "end-1" },
  ],
};

// ── Inner canvas (needs ReactFlowProvider wrapping it) ───────────────────────

let nodeCounter = 0;
function genId(type: string) {
  return `${type}-${++nodeCounter}-${Date.now()}`;
}

interface CanvasInnerProps {
  workflow: Workflow | null;
  initialNodes: Node[];
  initialEdges: Edge[];
}

function CanvasInner({ workflow, initialNodes, initialEdges }: CanvasInnerProps) {
  const router = useRouter();
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null);
  const { setNodes: rfSetNodes, setEdges: rfSetEdges } = useReactFlow();

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);

  // Top bar state
  const [workflowName, setWorkflowName] = useState(workflow?.name ?? "Untitled Workflow");
  const [workflowId, setWorkflowId] = useState<string | null>(workflow?.id ?? null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  // Run state
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const { events: runEvents, status: runStatus } = useRunStream(activeRunId);

  // Live logs panel
  const [logsOpen, setLogsOpen] = useState(false);
  const logsRef = useRef<HTMLDivElement>(null);

  // Template dropdown
  const [templateOpen, setTemplateOpen] = useState(false);

  // Scroll logs to bottom on new events
  useEffect(() => {
    if (logsRef.current) logsRef.current.scrollTop = logsRef.current.scrollHeight;
  }, [runEvents]);

  // Auto-open logs when run starts
  useEffect(() => {
    if (activeRunId) setLogsOpen(true);
  }, [activeRunId]);

  // ── Edge connect ────────────────────────────────────────────────────────────
  const onConnect = useCallback(
    (params: Connection) =>
      setEdges((eds) => addEdge({ ...params, animated: true }, eds)),
    [setEdges]
  );

  // ── Node selection ──────────────────────────────────────────────────────────
  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => setSelectedNode(node),
    []
  );
  const onPaneClick = useCallback(() => setSelectedNode(null), []);

  // ── Node data update from config panel ─────────────────────────────────────
  const handleNodeDataChange = useCallback(
    (nodeId: string, newData: Record<string, unknown>) => {
      setNodes((nds) =>
        nds.map((n) => (n.id === nodeId ? { ...n, data: newData } : n))
      );
      setSelectedNode((prev) =>
        prev?.id === nodeId ? { ...prev, data: newData } : prev
      );
    },
    [setNodes]
  );

  // ── Drag from palette ───────────────────────────────────────────────────────
  const onDragStart = (e: DragEvent, type: string, defaultData: Record<string, unknown>) => {
    e.dataTransfer.setData("application/reactflow-type", type);
    e.dataTransfer.setData("application/reactflow-data", JSON.stringify(defaultData));
    e.dataTransfer.effectAllowed = "move";
  };

  const onDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      if (!reactFlowWrapper.current || !rfInstance) return;

      const type = e.dataTransfer.getData("application/reactflow-type");
      if (!type) return;

      const defaultData = JSON.parse(
        e.dataTransfer.getData("application/reactflow-data") || "{}"
      );

      const bounds = reactFlowWrapper.current.getBoundingClientRect();
      const position = rfInstance.screenToFlowPosition({
        x: e.clientX - bounds.left,
        y: e.clientY - bounds.top,
      });

      const newNode: Node = {
        id: genId(type),
        type,
        position,
        data: defaultData,
      };

      setNodes((nds) => [...nds, newNode]);
    },
    [rfInstance, setNodes]
  );

  const onDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  // ── Save ────────────────────────────────────────────────────────────────────
  const handleSave = useCallback(async () => {
    if (!rfInstance) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const obj = rfInstance.toObject();
      const graphJson = { nodes: obj.nodes, edges: obj.edges };

      if (workflowId) {
        await updateWorkflow(workflowId, { name: workflowName, graph_json: graphJson });
        setSaveMsg("Saved");
      } else {
        const wf = await createWorkflow({
          name: workflowName,
          graph_json: graphJson,
          status: "active",
        });
        setWorkflowId(wf.id);
        setSaveMsg("Created");
        router.push(`/workflows/${wf.id}`);
      }
    } catch (err) {
      setSaveMsg(`Error: ${(err as Error).message}`);
    } finally {
      setSaving(false);
      setTimeout(() => setSaveMsg(null), 3000);
    }
  }, [rfInstance, workflowId, workflowName, router]);

  // ── Run ─────────────────────────────────────────────────────────────────────
  const handleRun = useCallback(async () => {
    if (!workflowId) {
      alert("Save the workflow first.");
      return;
    }
    setRunning(true);
    try {
      const run = await triggerRun(workflowId, { message: "Manual trigger from builder" });
      setActiveRunId(run.id);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setRunning(false);
    }
  }, [workflowId]);

  // ── Load template ────────────────────────────────────────────────────────────
  const loadTemplate = useCallback(
    async (tplKey: "payment_triage" | "support_escalation") => {
      setTemplateOpen(false);

      // First try to find an existing workflow with this template
      try {
        const workflows = await getWorkflows();
        const match = workflows.find((w) =>
          tplKey === "payment_triage"
            ? w.name.toLowerCase().includes("payment") || w.name.toLowerCase().includes("triage")
            : w.name.toLowerCase().includes("support") || w.name.toLowerCase().includes("escalation")
        );
        if (match && match.graph_json?.nodes) {
          const gj = match.graph_json as { nodes: Node[]; edges: Edge[] };
          rfSetNodes(gj.nodes ?? []);
          rfSetEdges(gj.edges ?? []);
          setWorkflowName(match.name);
          setWorkflowId(match.id);
          return;
        }
      } catch {
        // Fall through to hardcoded template
      }

      // Use hardcoded template
      const tpl = tplKey === "payment_triage" ? PAYMENT_TRIAGE_TEMPLATE : SUPPORT_ESCALATION_TEMPLATE;
      rfSetNodes(tpl.nodes);
      rfSetEdges(tpl.edges);
      setWorkflowName(tplKey === "payment_triage" ? "Payment Failure Triage" : "Support Escalation");
      setWorkflowId(null);
    },
    [rfSetNodes, rfSetEdges]
  );

  const logMessages = runEvents.map(
    (e) => `[${new Date(e.timestamp).toLocaleTimeString()}] ${e.event_type} — ${JSON.stringify(e.data).slice(0, 120)}`
  );

  return (
    <div className="flex flex-col h-full">
      {/* ── Top bar ── */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-slate-200 bg-white shrink-0">
        {/* Workflow name */}
        <input
          value={workflowName}
          onChange={(e) => setWorkflowName(e.target.value)}
          className="flex-1 min-w-0 px-2 py-1 text-sm font-medium text-slate-900 border border-transparent rounded-lg hover:border-slate-200 focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-400 transition-colors"
          placeholder="Workflow name…"
        />

        {saveMsg && (
          <span className={`text-xs px-2 py-1 rounded ${saveMsg.startsWith("Error") ? "text-red-600 bg-red-50" : "text-emerald-700 bg-emerald-50"}`}>
            {saveMsg}
          </span>
        )}

        {/* Template dropdown */}
        <div className="relative">
          <button
            onClick={() => setTemplateOpen((o) => !o)}
            className="flex items-center gap-1 px-3 py-1.5 text-sm border border-slate-200 text-slate-700 rounded-lg hover:bg-slate-50 transition-colors"
          >
            Templates
            <ChevronDown className="w-3.5 h-3.5" />
          </button>
          {templateOpen && (
            <div className="absolute right-0 top-9 z-50 w-52 bg-white border border-slate-200 rounded-xl shadow-lg overflow-hidden">
              <button
                onClick={() => loadTemplate("payment_triage")}
                className="w-full text-left px-4 py-2.5 text-sm text-slate-700 hover:bg-violet-50 transition-colors"
              >
                💳 Payment Failure Triage
              </button>
              <button
                onClick={() => loadTemplate("support_escalation")}
                className="w-full text-left px-4 py-2.5 text-sm text-slate-700 hover:bg-blue-50 transition-colors"
              >
                🎧 Support Escalation
              </button>
            </div>
          )}
        </div>

        {/* Save */}
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 text-white text-sm font-medium rounded-lg hover:bg-slate-700 disabled:opacity-60 transition-colors"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          Save
        </button>

        {/* Run */}
        <button
          onClick={handleRun}
          disabled={running || !workflowId}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 text-white text-sm font-medium rounded-lg hover:bg-violet-700 disabled:opacity-60 transition-colors"
          title={!workflowId ? "Save first to enable run" : undefined}
        >
          {running ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
          Run
        </button>

        {/* Open run detail */}
        {activeRunId && (
          <button
            onClick={() => router.push(`/runs/${activeRunId}`)}
            className={`text-xs px-2.5 py-1 rounded-lg border transition-colors ${
              runStatus === "completed"
                ? "text-emerald-700 border-emerald-200 bg-emerald-50"
                : runStatus === "failed"
                ? "text-red-600 border-red-200 bg-red-50"
                : "text-blue-600 border-blue-200 bg-blue-50 animate-pulse"
            }`}
          >
            Run: {runStatus}
          </button>
        )}
      </div>

      {/* ── Main area ── */}
      <div className="flex flex-1 min-h-0">

        {/* Left palette */}
        <div className="w-44 shrink-0 border-r border-slate-200 bg-slate-50 flex flex-col px-3 py-4 gap-2">
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-1">Nodes</p>
          {PALETTE_ITEMS.map((item) => (
            <div
              key={item.type}
              draggable
              onDragStart={(e) => onDragStart(e, item.type, item.defaultData)}
              className={`flex items-center gap-2.5 px-3 py-2.5 rounded-xl border-2 cursor-grab active:cursor-grabbing select-none ${item.color} transition-shadow hover:shadow-sm`}
            >
              {item.icon}
              <span className="text-xs font-medium text-slate-700">{item.label}</span>
            </div>
          ))}
          <div className="mt-auto text-[10px] text-slate-400 text-center pt-4">
            Drag nodes onto canvas
          </div>
        </div>

        {/* Canvas */}
        <div className="flex-1 min-w-0 relative" ref={reactFlowWrapper}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onInit={setRfInstance}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            onDrop={onDrop}
            onDragOver={onDragOver}
            nodeTypes={NODE_TYPES}
            snapToGrid
            snapGrid={[20, 20]}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            defaultEdgeOptions={{ animated: true, style: { stroke: "#8b5cf6", strokeWidth: 2 } }}
            className="bg-slate-50"
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#cbd5e1" />
            <Controls position="bottom-left" />
            <MiniMap
              position="bottom-right"
              nodeColor={(n) =>
                n.type === "agent" ? "#8b5cf6" :
                n.type === "condition" ? "#f59e0b" :
                n.type === "trigger" ? "#3b82f6" : "#10b981"
              }
              className="!border !border-slate-200 !rounded-xl !shadow"
            />
          </ReactFlow>
        </div>

        {/* Right config panel */}
        <div className="w-72 shrink-0 border-l border-slate-200 bg-white flex flex-col">
          <NodeConfigPanel node={selectedNode} onChange={handleNodeDataChange} />
        </div>
      </div>

      {/* ── Live logs panel ── */}
      <div
        className="shrink-0 border-t border-slate-200 bg-slate-950 transition-all"
        style={{ height: logsOpen ? 150 : 36 }}
      >
        <button
          onClick={() => setLogsOpen((o) => !o)}
          className="w-full flex items-center justify-between px-4 py-2 text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors"
        >
          <span>
            Live Logs
            {activeRunId && (
              <span className="ml-2 text-[10px] font-mono text-slate-500">
                run:{activeRunId.slice(0, 8)}
              </span>
            )}
          </span>
          {logsOpen
            ? <ChevronDown className="w-3.5 h-3.5" />
            : <ChevronUp className="w-3.5 h-3.5" />
          }
        </button>
        {logsOpen && (
          <div
            ref={logsRef}
            className="overflow-auto px-4 pb-3 space-y-0.5"
            style={{ height: 114 }}
          >
            {logMessages.length === 0 ? (
              <p className="text-[11px] text-slate-600 font-mono">
                {activeRunId ? "Waiting for events…" : "No active run. Press Run to start."}
              </p>
            ) : (
              logMessages.map((msg, i) => (
                <p key={i} className="text-[10px] text-slate-400 font-mono leading-relaxed">
                  {msg}
                </p>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Exported Canvas (wrapped in provider) ─────────────────────────────────────

interface CanvasProps {
  workflow?: Workflow | null;
  initialNodes?: Node[];
  initialEdges?: Edge[];
}

export function Canvas({ workflow = null, initialNodes = [], initialEdges = [] }: CanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner
        workflow={workflow}
        initialNodes={initialNodes}
        initialEdges={initialEdges}
      />
    </ReactFlowProvider>
  );
}
