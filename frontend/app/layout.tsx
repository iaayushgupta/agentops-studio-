import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/layout/Sidebar";

export const metadata: Metadata = {
  title: "Yuno Agent Platform",
  description: "AI Agent Orchestration Platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, -apple-system, sans-serif" }}>
        <div className="flex min-h-screen bg-slate-50">
          <Sidebar />
          <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
