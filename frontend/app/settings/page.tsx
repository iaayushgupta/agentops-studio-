"use client";

import { useState, useEffect, useRef } from "react";
import { CheckCircle2, GripVertical, Plus, Trash2, X } from "lucide-react";
import { Header } from "@/components/layout/Header";
import {
  getRunsList,
  getRunTimeline,
  getWorkflows,
  getRoutingRules,
  createRoutingRule,
  updateRoutingRule,
  deleteRoutingRule,
} from "@/lib/api";
import type { Workflow, RoutingRule } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

type BotStatus = "checking" | "connected" | "offline";

/** Local (potentially unsaved) routing rule state. id is undefined for new rows. */
interface LocalRule {
  id?: string;
  keywords: string[];
  workflow_id: string;
  priority: number;
  is_active: boolean;
}

// ── Static data ───────────────────────────────────────────────────────────────

const MODELS = [
  { role: "Primary",  provider: "Google AI Studio", model: "gemini-1.5-flash",        cost: "Free tier" },
  { role: "Fallback", provider: "Groq",             model: "llama-3.3-70b-versatile", cost: "Free tier" },
];

// ── Sub-components ────────────────────────────────────────────────────────────

function Badge({ variant }: { variant: "connected" | "offline" | "checking" | "active" }) {
  const styles = {
    connected: "bg-emerald-100 text-emerald-700",
    active:    "bg-emerald-100 text-emerald-700",
    offline:   "bg-red-100 text-red-600",
    checking:  "bg-slate-100 text-slate-500",
  };
  const dot = {
    connected: "bg-emerald-500",
    active:    "bg-emerald-500",
    offline:   "bg-red-500",
    checking:  "bg-slate-400",
  };
  const label = { connected: "Connected", active: "Active", offline: "Offline", checking: "Checking…" };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${styles[variant]}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot[variant]}`} />
      {label[variant]}
    </span>
  );
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: () => void }) {
  return (
    <button
      type="button"
      onClick={onChange}
      className={`relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors focus:outline-none
        ${checked ? "bg-violet-600" : "bg-slate-200"}`}
    >
      <span
        className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform
          ${checked ? "translate-x-4" : "translate-x-0.5"}`}
      />
    </button>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  // ── URL settings state ──────────────────────────────────────────────────────
  const [backendUrl, setBackendUrl] = useState("");
  const [wsUrl, setWsUrl] = useState("");
  const [urlSaved, setUrlSaved] = useState(false);

  // ── Bot / cost state ────────────────────────────────────────────────────────
  const [botStatus, setBotStatus] = useState<BotStatus>("checking");
  const [sessionCost, setSessionCost] = useState<number | null>(null);

  // ── Routing rules state ─────────────────────────────────────────────────────
  const [rules, setRules] = useState<LocalRule[]>([]);
  const [deletedIds, setDeletedIds] = useState<string[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [kwInputs, setKwInputs] = useState<Record<number, string>>({});
  const [rulesLoading, setRulesLoading] = useState(true);
  const [savingRules, setSavingRules] = useState(false);
  const [rulesSaved, setRulesSaved] = useState(false);
  const [rulesError, setRulesError] = useState("");

  // ── Drag state ──────────────────────────────────────────────────────────────
  const dragFromIdx = useRef<number | null>(null);

  // ── Load on mount ───────────────────────────────────────────────────────────
  useEffect(() => {
    const base =
      localStorage.getItem("BACKEND_URL") ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000";
    const ws =
      localStorage.getItem("WS_URL") ||
      process.env.NEXT_PUBLIC_WS_URL ||
      "ws://localhost:8000";
    setBackendUrl(base);
    setWsUrl(ws);

    // Health check
    fetch(`${base}/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data: { status: string }) =>
        setBotStatus(data.status === "ok" ? "connected" : "offline")
      )
      .catch(() => setBotStatus("offline"));

    // Cost this session
    getRunsList({ limit: 50 })
      .then(async (runs) => {
        const completedIds = runs.filter((r) => r.status === "completed").map((r) => r.id);
        if (completedIds.length === 0) { setSessionCost(0); return; }
        const timelines = await Promise.all(
          completedIds.map((id) => getRunTimeline(id).catch(() => null))
        );
        setSessionCost(timelines.reduce((acc, t) => acc + (t?.run?.total_cost_usd ?? 0), 0));
      })
      .catch(() => setSessionCost(0));

    // Routing rules + workflows
    Promise.all([getRoutingRules(), getWorkflows()])
      .then(([fetchedRules, fetchedWorkflows]) => {
        setWorkflows(fetchedWorkflows);
        setRules(
          fetchedRules.map((r) => ({
            id: r.id,
            keywords: r.keywords,
            workflow_id: r.workflow_id ?? fetchedWorkflows[0]?.id ?? "",
            priority: r.priority,
            is_active: r.is_active,
          }))
        );
      })
      .catch(() => setRulesError("Failed to load routing rules"))
      .finally(() => setRulesLoading(false));
  }, []);

  // ── URL Save ────────────────────────────────────────────────────────────────
  function handleUrlSave() {
    localStorage.setItem("BACKEND_URL", backendUrl.trim() || "http://localhost:8000");
    localStorage.setItem("WS_URL", wsUrl.trim() || "ws://localhost:8000");
    setUrlSaved(true);
    setTimeout(() => setUrlSaved(false), 4000);
  }

  // ── Drag-and-drop helpers (HTML5 native) ────────────────────────────────────
  function handleDragStart(idx: number) {
    dragFromIdx.current = idx;
  }
  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
  }
  function handleDrop(toIdx: number) {
    const fromIdx = dragFromIdx.current;
    if (fromIdx === null || fromIdx === toIdx) return;
    const reordered = [...rules];
    const [moved] = reordered.splice(fromIdx, 1);
    reordered.splice(toIdx, 0, moved);
    setRules(reordered);
    dragFromIdx.current = null;
  }
  function handleDragEnd() {
    dragFromIdx.current = null;
  }

  // ── Keyword helpers ─────────────────────────────────────────────────────────
  function commitKeyword(ruleIdx: number) {
    const raw = (kwInputs[ruleIdx] ?? "").trim().replace(/,+$/, "").trim();
    if (!raw) return;
    setRules((prev) =>
      prev.map((r, i) =>
        i === ruleIdx && !r.keywords.includes(raw)
          ? { ...r, keywords: [...r.keywords, raw] }
          : r
      )
    );
    setKwInputs((prev) => ({ ...prev, [ruleIdx]: "" }));
  }

  function removeKeyword(ruleIdx: number, kwIdx: number) {
    setRules((prev) =>
      prev.map((r, i) =>
        i === ruleIdx ? { ...r, keywords: r.keywords.filter((_, ki) => ki !== kwIdx) } : r
      )
    );
  }

  // ── Rule CRUD helpers ───────────────────────────────────────────────────────
  function addRule() {
    setRules((prev) => [
      ...prev,
      {
        keywords: [],
        workflow_id: workflows[0]?.id ?? "",
        priority: 0,
        is_active: true,
      },
    ]);
  }

  function removeRule(idx: number) {
    const rule = rules[idx];
    if (rule.id) setDeletedIds((prev) => [...prev, rule.id!]);
    setRules((prev) => prev.filter((_, i) => i !== idx));
    setKwInputs((prev) => {
      const next: Record<number, string> = {};
      Object.entries(prev).forEach(([k, v]) => {
        const ki = Number(k);
        if (ki < idx) next[ki] = v;
        else if (ki > idx) next[ki - 1] = v;
      });
      return next;
    });
  }

  function toggleRuleActive(idx: number) {
    setRules((prev) =>
      prev.map((r, i) => (i === idx ? { ...r, is_active: !r.is_active } : r))
    );
  }

  function changeRuleWorkflow(idx: number, wfId: string) {
    setRules((prev) =>
      prev.map((r, i) => (i === idx ? { ...r, workflow_id: wfId } : r))
    );
  }

  // ── Save all rules ──────────────────────────────────────────────────────────
  async function handleSaveRules() {
    setRulesError("");
    setSavingRules(true);
    try {
      // 1. Delete removed rules
      await Promise.all(deletedIds.map((id) => deleteRoutingRule(id)));

      // 2. Assign priority based on array position (top of list = highest priority)
      const withPriority = rules.map((r, i) => ({
        ...r,
        priority: rules.length - i,
      }));

      // 3. PUT existing rules, POST new rules
      await Promise.all(
        withPriority.map((rule) => {
          const body = {
            keywords: rule.keywords,
            workflow_id: rule.workflow_id || null,
            priority: rule.priority,
            is_active: rule.is_active,
          };
          return rule.id
            ? updateRoutingRule(rule.id, body)
            : createRoutingRule(body);
        })
      );

      // 4. Reload from server to sync IDs / priorities
      setDeletedIds([]);
      const [fresh, wfs] = await Promise.all([getRoutingRules(), getWorkflows()]);
      setWorkflows(wfs);
      setRules(
        fresh.map((r) => ({
          id: r.id,
          keywords: r.keywords,
          workflow_id: r.workflow_id ?? wfs[0]?.id ?? "",
          priority: r.priority,
          is_active: r.is_active,
        }))
      );

      setRulesSaved(true);
      setTimeout(() => setRulesSaved(false), 3000);
    } catch (err) {
      setRulesError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSavingRules(false);
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <>
      <Header title="Settings" subtitle="Platform configuration" />
      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-2xl space-y-5">

          {/* ── API Connection ──────────────────────────────────────────────── */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
            <h2 className="font-medium text-slate-900">API Connection</h2>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Backend URL
              </label>
              <input
                value={backendUrl}
                onChange={(e) => setBackendUrl(e.target.value)}
                placeholder="http://localhost:8000"
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white text-slate-900 font-mono focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent transition-shadow"
              />
              <p className="mt-1.5 text-xs text-slate-500">
                Default: http://localhost:8000. Change when deploying to a server.
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                WebSocket URL
              </label>
              <input
                value={wsUrl}
                onChange={(e) => setWsUrl(e.target.value)}
                placeholder="ws://localhost:8000"
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white text-slate-900 font-mono focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent transition-shadow"
              />
              <p className="mt-1.5 text-xs text-slate-500">
                Default: ws://localhost:8000. Use wss:// for HTTPS deployments.
              </p>
            </div>

            <div className="flex items-center gap-3 pt-1">
              <button
                onClick={handleUrlSave}
                className="px-4 py-2 bg-violet-600 hover:bg-violet-700 active:bg-violet-800 text-white text-sm font-medium rounded-lg transition-colors"
              >
                Save
              </button>
              {urlSaved && (
                <span className="flex items-center gap-1.5 text-sm text-emerald-600">
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  Settings saved. Refresh the page to apply.
                </span>
              )}
            </div>
          </div>

          {/* ── Telegram Configuration ──────────────────────────────────────── */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
            <h2 className="font-medium text-slate-900">Telegram Configuration</h2>

            <div className="flex items-center justify-between py-2 border-b border-slate-100">
              <span className="text-sm text-slate-700">Bot Status</span>
              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-500 font-mono">Telegram Bot</span>
                <Badge variant={botStatus} />
              </div>
            </div>

            <div className="flex items-center justify-between py-2">
              <span className="text-sm text-slate-700">Default Workflow</span>
              <div className="text-right">
                <p className="text-sm font-medium text-slate-900">Payment Failure Triage</p>
                <p className="text-xs text-slate-400">Used when no routing rule matches</p>
              </div>
            </div>
          </div>

          {/* ── Smart Routing Rules ─────────────────────────────────────────── */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
            <div>
              <h2 className="font-medium text-slate-900">Smart Routing Rules</h2>
              <p className="text-sm text-slate-500 mt-0.5 leading-relaxed">
                Incoming Telegram messages are automatically routed to the correct workflow
                based on keywords. Rules are checked in priority order — first match wins.
                Drag to reorder.
              </p>
            </div>

            {rulesLoading ? (
              <div className="py-8 text-center text-sm text-slate-400">Loading rules…</div>
            ) : (
              <>
                {/* Rule rows */}
                <div className="space-y-2">
                  {rules.length === 0 && (
                    <div className="py-6 text-center text-sm text-slate-400 border border-dashed border-slate-200 rounded-lg">
                      No routing rules. Click &ldquo;Add Rule&rdquo; to create one.
                    </div>
                  )}

                  {rules.map((rule, idx) => (
                    <div
                      key={idx}
                      draggable
                      onDragStart={() => handleDragStart(idx)}
                      onDragOver={handleDragOver}
                      onDrop={() => handleDrop(idx)}
                      onDragEnd={handleDragEnd}
                      className="flex items-start gap-2 p-3 rounded-lg border border-slate-200 bg-white hover:bg-slate-50/50 transition-colors"
                    >
                      {/* Drag handle */}
                      <div className="mt-1.5 flex-shrink-0 cursor-grab active:cursor-grabbing text-slate-300 hover:text-slate-500 transition-colors">
                        <GripVertical className="w-4 h-4" />
                      </div>

                      {/* Keywords tag input */}
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap gap-1 items-center min-h-[28px]">
                          {rule.keywords.map((kw, ki) => (
                            <span
                              key={ki}
                              className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full bg-violet-100 text-violet-700 text-xs"
                            >
                              {kw}
                              <button
                                onClick={() => removeKeyword(idx, ki)}
                                className="ml-0.5 hover:text-violet-900 focus:outline-none"
                                aria-label={`Remove keyword ${kw}`}
                              >
                                <X className="w-3 h-3" />
                              </button>
                            </span>
                          ))}
                          <input
                            value={kwInputs[idx] ?? ""}
                            onChange={(e) =>
                              setKwInputs((prev) => ({ ...prev, [idx]: e.target.value }))
                            }
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === ",") {
                                e.preventDefault();
                                commitKeyword(idx);
                              }
                              if (
                                e.key === "Backspace" &&
                                !kwInputs[idx] &&
                                rule.keywords.length > 0
                              ) {
                                removeKeyword(idx, rule.keywords.length - 1);
                              }
                            }}
                            onBlur={() => commitKeyword(idx)}
                            placeholder={rule.keywords.length === 0 ? "Type keyword, press Enter…" : "+keyword"}
                            className="flex-1 min-w-[100px] max-w-[160px] px-2 py-0.5 text-xs rounded-full border border-dashed border-slate-300 focus:outline-none focus:border-violet-400 bg-transparent placeholder:text-slate-400"
                          />
                        </div>
                      </div>

                      {/* Workflow dropdown */}
                      <select
                        value={rule.workflow_id}
                        onChange={(e) => changeRuleWorkflow(idx, e.target.value)}
                        className="flex-shrink-0 px-2 py-1.5 text-xs border border-slate-200 rounded-lg bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-violet-500 max-w-[160px] truncate"
                      >
                        {workflows.map((w) => (
                          <option key={w.id} value={w.id}>
                            {w.name}
                          </option>
                        ))}
                        {workflows.length === 0 && (
                          <option value="">No workflows</option>
                        )}
                      </select>

                      {/* Active toggle */}
                      <div className="flex-shrink-0 mt-0.5">
                        <Toggle
                          checked={rule.is_active}
                          onChange={() => toggleRuleActive(idx)}
                        />
                      </div>

                      {/* Delete */}
                      <button
                        onClick={() => removeRule(idx)}
                        className="flex-shrink-0 mt-0.5 text-slate-300 hover:text-red-500 transition-colors focus:outline-none"
                        aria-label="Delete rule"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>

                {/* Add Rule */}
                <button
                  onClick={addRule}
                  disabled={workflows.length === 0}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-600 border border-dashed border-slate-300 rounded-lg hover:border-violet-400 hover:text-violet-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Add Rule
                </button>

                {/* Save All footer */}
                <div className="flex items-center gap-3 pt-2 border-t border-slate-100">
                  <button
                    onClick={handleSaveRules}
                    disabled={savingRules}
                    className="px-4 py-2 bg-violet-600 hover:bg-violet-700 active:bg-violet-800 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-60"
                  >
                    {savingRules ? "Saving…" : "Save All Rules"}
                  </button>
                  {rulesSaved && (
                    <span className="flex items-center gap-1.5 text-sm text-emerald-600">
                      <CheckCircle2 className="w-4 h-4 shrink-0" />
                      Rules saved successfully
                    </span>
                  )}
                  {rulesError && (
                    <span className="text-sm text-red-600">{rulesError}</span>
                  )}
                </div>

                <p className="text-xs text-slate-400 leading-relaxed">
                  Default fallback: <span className="font-medium text-slate-500">Payment Failure Triage</span>{" "}
                  (used when no keywords match)
                </p>
              </>
            )}
          </div>

          {/* ── Model Configuration ─────────────────────────────────────────── */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
            <h2 className="font-medium text-slate-900">Model Configuration</h2>

            <div className="overflow-hidden rounded-lg border border-slate-200">
              <table className="w-full text-sm">
                <thead className="border-b border-slate-200 bg-slate-50">
                  <tr>
                    {["Role", "Provider", "Model", "Cost", "Status"].map((h) => (
                      <th
                        key={h}
                        className="px-4 py-2 text-left text-xs font-medium uppercase tracking-wide text-slate-500"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {MODELS.map((m) => (
                    <tr key={m.role} className="hover:bg-slate-50/50">
                      <td className="px-4 py-2.5 font-medium text-slate-900">{m.role}</td>
                      <td className="px-4 py-2.5 text-slate-600">{m.provider}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-slate-500">{m.model}</td>
                      <td className="px-4 py-2.5 text-slate-500">{m.cost}</td>
                      <td className="px-4 py-2.5">
                        <Badge variant="active" />
                      </td>
                    </tr>
                  ))}
                  <tr className="bg-slate-50">
                    <td colSpan={3} className="px-4 py-2.5 text-sm font-medium text-slate-700">
                      Cost This Session
                    </td>
                    <td colSpan={2} className="px-4 py-2.5 text-sm font-semibold text-slate-900">
                      {sessionCost === null ? (
                        <span className="text-slate-400">Loading…</span>
                      ) : (
                        `$${sessionCost.toFixed(4)}`
                      )}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <p className="text-xs text-slate-400 leading-relaxed">
              Cost estimates use a static price table. Verify at provider pricing pages before
              production use.
            </p>
          </div>

          {/* ── About ───────────────────────────────────────────────────────── */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-2">
            <h2 className="font-medium text-slate-900">About</h2>
            <dl className="space-y-1 text-sm text-slate-600">
              <div className="flex gap-2">
                <dt className="font-medium w-28">Project</dt>
                <dd>AgentOps Studio</dd>
              </div>
              <div className="flex gap-2">
                <dt className="font-medium w-28">Stack</dt>
                <dd>FastAPI + LangGraph + Next.js 14</dd>
              </div>
              <div className="flex gap-2">
                <dt className="font-medium w-28">LLM</dt>
                <dd>Gemini 1.5 Flash (primary), Groq llama-3.3-70b (fallback)</dd>
              </div>
              <div className="flex gap-2">
                <dt className="font-medium w-28">Version</dt>
                <dd>0.1.0</dd>
              </div>
            </dl>
          </div>

        </div>
      </div>
    </>
  );
}
