"use client";

import { useState } from "react";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Dashboard } from "@/components/dashboard/Dashboard";
import { TradesTab } from "@/components/trades/TradesTab";
import { ConfigTab } from "@/components/config/ConfigTab";
import { SettingsTab } from "@/components/settings/SettingsTab";

type Tab = "dashboard" | "trades" | "config" | "settings";

export default function Home() {
  const [tab, setTab] = useState<Tab>("dashboard");

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-surface px-4">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <div className="grid h-7 w-7 place-items-center rounded-md bg-accent/15 text-accent">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 17l5-6 4 4 5-7 4 5" />
              </svg>
            </div>
            <span className="text-sm font-semibold tracking-tight">Glyphh</span>
          </div>
          <nav className="flex items-center gap-1">
            {(["dashboard", "trades", "config", "settings"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium capitalize transition-colors ${
                  tab === t
                    ? "bg-surface-3 text-text"
                    : "text-text-muted hover:text-text"
                }`}
              >
                {t}
              </button>
            ))}
          </nav>
        </div>
        <ThemeToggle />
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto">
        {tab === "dashboard" && <Dashboard />}
        {tab === "trades" && <TradesTab />}
        {tab === "config" && <ConfigTab />}
        {tab === "settings" && <SettingsTab />}
      </main>
    </div>
  );
}
