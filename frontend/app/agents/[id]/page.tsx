"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { Header } from "@/components/layout/Header";
import { getAgent, updateAgent } from "@/lib/api";
import type { Agent, AgentUpdate, ChannelBindings } from "@/lib/api";

const AVAILABLE_TOOLS = [
  "get_transaction",
  "get_psp_status",
  "check_routing_logs",
  "suggest_alternate_psp",
  "send_telegram_message",
  "calculator",
];

function Label({ children }: { children: React.ReactNode }) {
  return <label className="block text-sm font-medium text-slate-700 mb-1">{children}</label>;
}

function Hint({ children }: { children: React.ReactNode }) {
  return <p className="mt-1 text-xs text-slate-400">{children}</p>;
}

function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full px-3 py-2 border border-slate-200 rounded-lg text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent ${props.className ?? ""}`}
    />
  );
}

function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={`w-full px-3 py-2 border border-slate-200 rounded-lg text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent resize-none ${props.className ?? ""}`}
    />
  );
}

function ToggleSwitch({
  checked,
  onChange,
  disabled = false,
}: {
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={onChange}
      className={`relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 ${
        checked ? "bg-violet-600" : "bg-slate-200"
      } ${disabled ? "cursor-not-allowed opacity-40" : "cursor-pointer"}`}
    >
      <span
        className={`pointer-events-none block h-4 w-4 rounded-full bg-white shadow-lg transition-transform ${
          checked ? "translate-x-4" : "translate-x-0"
        }`}
      />
    </button>
  );
}

export default function EditAgentPage() {
  const router = useRouter();
  const params = useParams();
  const id = params.id as string;

  const [agent, setAgent] = useState<Agent | null>(null);
  const [form, setForm] = useState<AgentUpdate>({});
  const [channelBindings, setChannelBindings] = useState<
    Required<Pick<ChannelBindings, "telegram">>
  >({
    telegram: { enabled: false, chat_id: "" },
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAgent(id)
      .then((a) => {
        setAgent(a);
        setForm({
          name: a.name,
          description: a.description ?? "",
          role: a.role ?? "",
          system_prompt: a.system_prompt,
          tools_enabled: a.tools_enabled,
          model_provider: a.model_provider,
          model_name: a.model_name,
          temperature: a.temperature,
          memory_enabled: a.memory_enabled,
          max_iterations: a.max_iterations,
          max_cost_usd: a.max_cost_usd,
        });
        // Populate channel bindings from saved agent data
        const cb = a.channel_bindings;
        if (cb?.telegram) {
          setChannelBindings({
            telegram: {
              enabled: cb.telegram.enabled ?? false,
              chat_id: cb.telegram.chat_id ?? "",
            },
          });
        }
      })
      .catch((err) => setError((err as Error).message))
      .finally(() => setLoading(false));
  }, [id]);

  function setTelegram<K extends "enabled" | "chat_id">(
    key: K,
    value: K extends "enabled" ? boolean : string
  ) {
    setChannelBindings((prev) => ({
      ...prev,
      telegram: { ...prev.telegram, [key]: value },
    }));
  }

  function set<K extends keyof AgentUpdate>(key: K, value: AgentUpdate[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function toggleTool(tool: string) {
    const current = form.tools_enabled ?? agent?.tools_enabled ?? [];
    set(
      "tools_enabled",
      current.includes(tool) ? current.filter((t) => t !== tool) : [...current, tool]
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await updateAgent(id, { ...form, channel_bindings: channelBindings });
      router.push("/agents");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="p-10 text-slate-400 text-sm">Loading…</div>;
  if (!agent) return <div className="p-10 text-red-500 text-sm">{error}</div>;

  const tools = form.tools_enabled ?? agent.tools_enabled;

  return (
    <>
      <Header title={`Edit: ${agent.name}`} subtitle="Update agent configuration" />

      <div className="flex-1 overflow-auto p-6">
        <form onSubmit={handleSubmit} className="max-w-2xl space-y-6">
          <section className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
            <h2 className="font-medium text-slate-900">Identity</h2>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Name</label>
              <Input value={form.name ?? ""} onChange={(e) => set("name", e.target.value)} />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Role</label>
              <Input value={form.role ?? ""} onChange={(e) => set("role", e.target.value)} />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Description</label>
              <Textarea rows={2} value={form.description ?? ""} onChange={(e) => set("description", e.target.value)} />
            </div>
          </section>

          <section className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
            <h2 className="font-medium text-slate-900">System Prompt</h2>
            <Textarea rows={8} value={form.system_prompt ?? ""} onChange={(e) => set("system_prompt", e.target.value)} />
          </section>

          <section className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
            <h2 className="font-medium text-slate-900">Enabled Tools</h2>
            <div className="flex flex-wrap gap-2">
              {AVAILABLE_TOOLS.map((tool) => (
                <button
                  key={tool}
                  type="button"
                  onClick={() => toggleTool(tool)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                    tools.includes(tool)
                      ? "bg-violet-600 text-white border-violet-600"
                      : "bg-white text-slate-600 border-slate-200 hover:border-violet-400"
                  }`}
                >
                  {tool}
                </button>
              ))}
            </div>
          </section>

          {/* Channel Bindings */}
          <section className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
            <div>
              <h2 className="font-medium text-slate-900">Channel Bindings</h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Connect this agent to external messaging channels
              </p>
            </div>

            <div className="space-y-4">

              {/* Telegram */}
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <ToggleSwitch
                    checked={channelBindings.telegram.enabled}
                    onChange={() =>
                      setTelegram("enabled", !channelBindings.telegram.enabled)
                    }
                  />
                  <span className="text-sm font-medium text-slate-700">Telegram</span>
                </div>
                {channelBindings.telegram.enabled && (
                  <div className="ml-12 space-y-1.5">
                    <Label>Chat ID</Label>
                    <Input
                      value={channelBindings.telegram.chat_id}
                      onChange={(e) => setTelegram("chat_id", e.target.value)}
                      placeholder="e.g. 123456789"
                    />
                    <Hint>
                      Get your chat ID by messaging @userinfobot on Telegram
                    </Hint>
                  </div>
                )}
              </div>

              {/* Slack — coming soon */}
              <div className="flex items-center gap-3">
                <ToggleSwitch checked={false} onChange={() => {}} disabled />
                <span className="text-sm font-medium text-slate-400">Slack</span>
                <span className="px-1.5 py-0.5 text-xs font-medium bg-slate-100 text-slate-500 rounded">
                  Coming Soon
                </span>
              </div>

              {/* WhatsApp — coming soon */}
              <div className="flex items-center gap-3">
                <ToggleSwitch checked={false} onChange={() => {}} disabled />
                <span className="text-sm font-medium text-slate-400">WhatsApp</span>
                <span className="px-1.5 py-0.5 text-xs font-medium bg-slate-100 text-slate-500 rounded">
                  Coming Soon
                </span>
              </div>

            </div>
          </section>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
              {error}
            </p>
          )}

          <div className="flex gap-3 pb-6">
            <button
              type="submit"
              disabled={saving}
              className="px-5 py-2 bg-violet-600 text-white text-sm font-medium rounded-lg hover:bg-violet-700 disabled:opacity-60 transition-colors"
            >
              {saving ? "Saving…" : "Save Changes"}
            </button>
            <button
              type="button"
              onClick={() => router.push("/agents")}
              className="px-5 py-2 border border-slate-200 text-slate-700 text-sm font-medium rounded-lg hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </>
  );
}
