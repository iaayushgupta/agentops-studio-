"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Bot,
  GitFork,
  PlayCircle,
  Terminal,
  Settings,
  Zap,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/workflows", label: "Workflows", icon: GitFork },
  { href: "/runs", label: "Runs", icon: PlayCircle },
  { href: "/playground", label: "Playground", icon: Terminal },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex flex-col w-60 min-h-screen bg-sidebar text-slate-300 shrink-0">
      {/* Brand */}
      <div className="flex items-center gap-2 px-5 py-5 border-b border-slate-700/50">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-violet-600">
          <Zap className="w-4 h-4 text-white" />
        </div>
        <span className="text-white font-semibold tracking-tight text-lg">
          Yuno
        </span>
        <span className="text-slate-500 text-xs ml-auto">v0.1</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const isActive =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-slate-700/70 text-white"
                  : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
              }`}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-slate-700/50 text-xs text-slate-600">
        Yuno Agent Platform
      </div>
    </aside>
  );
}
