"use client";

import { Header } from "@/components/layout/Header";

export default function SettingsPage() {
  return (
    <>
      <Header title="Settings" subtitle="Platform configuration" />
      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-2xl space-y-5">

          <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
            <h2 className="font-medium text-slate-900">API Connection</h2>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Backend URL</label>
              <input
                readOnly
                value={process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-slate-50 text-slate-500 font-mono"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">WebSocket URL</label>
              <input
                readOnly
                value={process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000"}
                className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-slate-50 text-slate-500 font-mono"
              />
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-2">
            <h2 className="font-medium text-slate-900">About</h2>
            <dl className="space-y-1 text-sm text-slate-600">
              <div className="flex gap-2"><dt className="font-medium w-28">Project</dt><dd>Yuno Agent Platform</dd></div>
              <div className="flex gap-2"><dt className="font-medium w-28">Stack</dt><dd>FastAPI + LangGraph + Next.js 14</dd></div>
              <div className="flex gap-2"><dt className="font-medium w-28">LLM</dt><dd>Gemini 1.5 Flash (primary), Groq llama-3.3-70b (fallback)</dd></div>
              <div className="flex gap-2"><dt className="font-medium w-28">Version</dt><dd>0.1.0</dd></div>
            </dl>
          </div>

        </div>
      </div>
    </>
  );
}
