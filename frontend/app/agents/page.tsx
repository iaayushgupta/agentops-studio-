"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Pencil, Trash2, Bot } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { getAgents, deleteAgent } from "@/lib/api";
import type { Agent, ChannelBindings } from "@/lib/api";

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      setAgents(await getAgents());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleDelete(id: string, name: string) {
    if (!confirm(`Delete agent "${name}"? This cannot be undone.`)) return;
    setDeletingId(id);
    try {
      await deleteAgent(id);
      setAgents((prev) => prev.filter((a) => a.id !== id));
    } catch (err) {
      alert(`Failed to delete: ${(err as Error).message}`);
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <>
      <Header
        title="Agents"
        subtitle="Configure and manage AI agents"
        actions={
          <Link
            href="/agents/new"
            className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 text-white text-sm font-medium rounded-lg hover:bg-violet-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Agent
          </Link>
        }
      />

      <div className="flex-1 overflow-auto p-6">
        {loading ? (
          <div className="text-center text-slate-400 py-20 text-sm">Loading agents…</div>
        ) : agents.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-20 text-slate-400">
            <Bot className="w-10 h-10" />
            <p className="text-sm">No agents yet.</p>
            <Link
              href="/agents/new"
              className="text-sm text-violet-600 hover:underline"
            >
              Create your first agent →
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
            {agents.map((agent) => (
              <div
                key={agent.id}
                className="bg-white border border-slate-200 rounded-xl p-5 flex flex-col gap-3"
              >
                {/* Title row */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className="w-9 h-9 rounded-lg bg-violet-50 flex items-center justify-center shrink-0">
                      <Bot className="w-4 h-4 text-violet-600" />
                    </div>
                    <div>
                      <p className="font-medium text-slate-900 leading-tight">{agent.name}</p>
                      {agent.role && (
                        <p className="text-xs text-slate-400 mt-0.5">{agent.role}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <Link
                      href={`/agents/${agent.id}`}
                      className="p-1.5 text-slate-400 hover:text-violet-600 hover:bg-violet-50 rounded-lg transition-colors"
                      title="Edit"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </Link>
                    <button
                      onClick={() => handleDelete(agent.id, agent.name)}
                      disabled={deletingId === agent.id}
                      className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50"
                      title="Delete"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* Description */}
                {agent.description && (
                  <p className="text-xs text-slate-500 leading-relaxed line-clamp-2">
                    {agent.description}
                  </p>
                )}

                {/* Meta chips */}
                <div className="flex flex-wrap gap-1.5 mt-auto pt-1">
                  <span className="inline-flex px-2 py-0.5 rounded text-xs bg-slate-100 text-slate-600">
                    {agent.model_provider}/{agent.model_name}
                  </span>
                  <span className="inline-flex px-2 py-0.5 rounded text-xs bg-slate-100 text-slate-600">
                    temp {agent.temperature}
                  </span>
                  {agent.memory_enabled && (
                    <span className="inline-flex px-2 py-0.5 rounded text-xs bg-emerald-100 text-emerald-700">
                      memory
                    </span>
                  )}
                  {agent.tools_enabled.length > 0 && (
                    <span className="inline-flex px-2 py-0.5 rounded text-xs bg-blue-100 text-blue-700">
                      {agent.tools_enabled.length} tool{agent.tools_enabled.length !== 1 ? "s" : ""}
                    </span>
                  )}
                  {(agent.channel_bindings as ChannelBindings | undefined)?.telegram?.enabled && (
                    <span className="inline-flex px-2 py-0.5 rounded text-xs border border-sky-200 bg-sky-50 text-sky-700">
                      📱 Telegram
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
