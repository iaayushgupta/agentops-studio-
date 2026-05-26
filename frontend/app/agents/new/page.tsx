"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Header } from "@/components/layout/Header";
import { createAgent } from "@/lib/api";
import type { AgentCreate, ChannelBindings } from "@/lib/api";

const AVAILABLE_TOOLS = [
  "get_transaction",
  "get_psp_status",
  "check_routing_logs",
  "suggest_alternate_psp",
  "send_telegram_message",
  "calculator",
];

const MODEL_PROVIDERS = ["google", "groq", "ollama"];
const MODEL_NAMES: Record<string, string[]> = {
  google: ["gemini-1.5-flash", "gemini-1.5-pro"],
  groq: ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
  ollama: ["llama3", "mistral"],
};

// ── Small form primitives ─────────────────────────────────────────────────────

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

function Select(props: React.SelectHTMLAttributes<HTMLSelectElement> & { children: React.ReactNode }) {
  return (
    <select
      {...props}
      className={`w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent ${props.className ?? ""}`}
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

// ── Page ─────────────────────────────────────────────────────────────────────

export default function NewAgentPage() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState<AgentCreate>({
    name: "",
    description: "",
    role: "",
    system_prompt: "",
    tools_enabled: [],
    model_provider: "google",
    model_name: "gemini-1.5-flash",
    temperature: 0.3,
    memory_enabled: false,
    max_iterations: 10,
    max_cost_usd: 1.0,
  });

  const [channelBindings, setChannelBindings] = useState<
    Required<Pick<ChannelBindings, "telegram">>
  >({
    telegram: { enabled: false, chat_id: "" },
  });

  function setTelegram<K extends "enabled" | "chat_id">(
    key: K,
    value: K extends "enabled" ? boolean : string
  ) {
    setChannelBindings((prev) => ({
      ...prev,
      telegram: { ...prev.telegram, [key]: value },
    }));
  }

  function set<K extends keyof AgentCreate>(key: K, value: AgentCreate[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function toggleTool(tool: string) {
    set(
      "tools_enabled",
      form.tools_enabled?.includes(tool)
        ? form.tools_enabled.filter((t) => t !== tool)
        : [...(form.tools_enabled ?? []), tool]
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) { setError("Name is required."); return; }
    if (!form.system_prompt.trim()) { setError("System prompt is required."); return; }
    setSaving(true);
    setError(null);
    try {
      await createAgent({ ...form, channel_bindings: channelBindings });
      router.push("/agents");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const availableModels = MODEL_NAMES[form.model_provider ?? "google"] ?? [];

  return (
    <>
      <Header
        title="New Agent"
        subtitle="Configure a new AI agent"
      />

      <div className="flex-1 overflow-auto p-6">
        <form onSubmit={handleSubmit} className="max-w-2xl space-y-6">

          {/* Identity */}
          <section className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
            <h2 className="font-medium text-slate-900">Identity</h2>

            <div>
              <Label>Name *</Label>
              <Input
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="e.g. Intake Agent"
              />
            </div>

            <div>
              <Label>Role</Label>
              <Input
                value={form.role ?? ""}
                onChange={(e) => set("role", e.target.value)}
                placeholder="e.g. triage, resolver, reviewer"
              />
              <Hint>Short functional label shown in the UI.</Hint>
            </div>

            <div>
              <Label>Description</Label>
              <Textarea
                rows={2}
                value={form.description ?? ""}
                onChange={(e) => set("description", e.target.value)}
                placeholder="What does this agent do?"
              />
            </div>
          </section>

          {/* System Prompt */}
          <section className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
            <h2 className="font-medium text-slate-900">System Prompt *</h2>
            <Textarea
              rows={8}
              value={form.system_prompt}
              onChange={(e) => set("system_prompt", e.target.value)}
              placeholder="You are a payment triage agent. Respond ONLY with valid JSON..."
            />
            <Hint>
              The agent will strictly follow this prompt on every invocation.
            </Hint>
          </section>

          {/* Model */}
          <section className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
            <h2 className="font-medium text-slate-900">Model</h2>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Provider</Label>
                <Select
                  value={form.model_provider}
                  onChange={(e) => {
                    const p = e.target.value;
                    set("model_provider", p);
                    set("model_name", MODEL_NAMES[p]?.[0] ?? "");
                  }}
                >
                  {MODEL_PROVIDERS.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </Select>
              </div>

              <div>
                <Label>Model</Label>
                <Select
                  value={form.model_name}
                  onChange={(e) => set("model_name", e.target.value)}
                >
                  {availableModels.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </Select>
              </div>
            </div>

            <div>
              <Label>Temperature ({form.temperature})</Label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={form.temperature}
                onChange={(e) => set("temperature", parseFloat(e.target.value))}
                className="w-full accent-violet-600"
              />
              <div className="flex justify-between text-xs text-slate-400 mt-0.5">
                <span>Deterministic (0)</span>
                <span>Creative (1)</span>
              </div>
            </div>
          </section>

          {/* Tools */}
          <section className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
            <h2 className="font-medium text-slate-900">Enabled Tools</h2>
            <div className="flex flex-wrap gap-2">
              {AVAILABLE_TOOLS.map((tool) => {
                const active = form.tools_enabled?.includes(tool);
                return (
                  <button
                    key={tool}
                    type="button"
                    onClick={() => toggleTool(tool)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                      active
                        ? "bg-violet-600 text-white border-violet-600"
                        : "bg-white text-slate-600 border-slate-200 hover:border-violet-400"
                    }`}
                  >
                    {tool}
                  </button>
                );
              })}
            </div>
          </section>

          {/* Limits */}
          <section className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
            <h2 className="font-medium text-slate-900">Limits</h2>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Max Iterations</Label>
                <Input
                  type="number"
                  min={1}
                  max={50}
                  value={form.max_iterations}
                  onChange={(e) => set("max_iterations", parseInt(e.target.value))}
                />
              </div>
              <div>
                <Label>Max Cost (USD)</Label>
                <Input
                  type="number"
                  min={0}
                  step={0.01}
                  value={form.max_cost_usd}
                  onChange={(e) => set("max_cost_usd", parseFloat(e.target.value))}
                />
              </div>
            </div>

            <div className="flex items-center gap-3">
              <input
                id="memory"
                type="checkbox"
                checked={form.memory_enabled}
                onChange={(e) => set("memory_enabled", e.target.checked)}
                className="w-4 h-4 accent-violet-600"
              />
              <label htmlFor="memory" className="text-sm text-slate-700">
                Enable memory (conversation history across runs)
              </label>
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

          {/* Error */}
          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
              {error}
            </p>
          )}

          {/* Actions */}
          <div className="flex gap-3 pb-6">
            <button
              type="submit"
              disabled={saving}
              className="px-5 py-2 bg-violet-600 text-white text-sm font-medium rounded-lg hover:bg-violet-700 disabled:opacity-60 transition-colors"
            >
              {saving ? "Saving…" : "Create Agent"}
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
