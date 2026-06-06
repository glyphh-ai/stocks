"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { GlyphTemplate } from "@/lib/types";
import { segmentAt, type Selection } from "@/lib/glyph";
import { Field, TextInput } from "./fields";

export function TestPanel({
  template,
  selection,
}: {
  template: GlyphTemplate;
  selection: Selection;
}) {
  const segment = segmentAt(template, selection);
  const [symbol, setSymbol] = useState(template.symbol || "AAPL");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    if (!segment) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.testSegment(symbol, template.interval, segment);
      if (res.error) setError(res.error);
      else setResult(res.roles);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold">Test</h2>
        <p className="text-xs text-text-muted">Run the selected segment&apos;s job in isolation</p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {!segment ? (
          <p className="text-sm text-text-muted">Select a segment or role to test its job.</p>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="rounded-lg border border-border bg-surface-2 px-3 py-2">
              <span className="text-xs text-text-muted">segment</span>
              <div className="text-sm font-medium">{segment.key}</div>
            </div>

            <Field label="Symbol">
              <TextInput value={symbol} onChange={(e) => setSymbol(e.target.value)} />
            </Field>

            <button
              onClick={run}
              disabled={running}
              className="rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {running ? "Running…" : "Run segment"}
            </button>

            {error && (
              <div className="rounded-lg border border-bad/40 bg-bad/10 p-3 text-xs">
                <div className="mb-1 font-semibold text-bad">Failed</div>
                <pre className="whitespace-pre-wrap break-words font-mono text-text-muted">{error}</pre>
                {error.includes("no tool registered") && (
                  <p className="mt-2 text-text-muted">
                    This step calls a tool that isn&apos;t registered on the server. Pick a registered tool or add it in <code className="text-text">app/jobs/tools.py</code>.
                  </p>
                )}
                {error.includes("StubLLMExecutor") && (
                  <p className="mt-2 text-text-muted">
                    This job has an llm step but no ANTHROPIC_API_KEY is set, so the stub executor refused it.
                  </p>
                )}
              </div>
            )}

            {result && (
              <div>
                <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                  Role values
                </span>
                <div className="overflow-hidden rounded-lg border border-border">
                  {Object.entries(result).map(([k, v], i) => (
                    <div
                      key={k}
                      className={`flex items-center justify-between gap-3 px-3 py-2 text-sm ${i % 2 ? "bg-surface" : "bg-surface-2"}`}
                    >
                      <span className="text-text-muted">{k}</span>
                      <span className="font-mono font-medium">{String(v)}</span>
                    </div>
                  ))}
                  {Object.keys(result).length === 0 && (
                    <div className="px-3 py-2 text-sm text-text-muted">No roles set.</div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
