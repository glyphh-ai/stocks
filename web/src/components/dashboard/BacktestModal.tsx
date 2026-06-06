"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { BacktestAnalysis, BacktestResult } from "@/lib/types";
import { BacktestChart } from "./BacktestChart";
import { Spinner } from "../Spinner";

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "good" | "bad" | "warn";
}) {
  const color =
    tone === "good"
      ? "text-good"
      : tone === "bad"
        ? "text-bad"
        : tone === "warn"
          ? "text-text"
          : "text-text";
  return (
    <div className="rounded-lg border border-border bg-surface-2 p-2.5">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
        {label}
      </div>
      <div className={`mt-0.5 text-base font-semibold tabular-nums ${color}`}>
        {value}
      </div>
    </div>
  );
}

const VERDICT_LABEL: Record<string, string> = {
  signal: "Signal",
  inconclusive: "Inconclusive",
  no_signal: "No signal",
};

const IMPACT_TONE: Record<string, string> = {
  high: "bg-good/15 text-good",
  medium: "bg-accent/15 text-accent",
  low: "bg-surface-3 text-text-muted",
};

export function BacktestModal({
  symbol,
  interval,
  onClose,
}: {
  symbol: string;
  interval: string;
  onClose: () => void;
}) {
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<BacktestAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .backtest(symbol, interval)
      .then((r) => alive && setResult(r))
      .catch((e) => alive && setError(e instanceof Error ? e.message : "Backtest failed"));
    return () => {
      alive = false;
    };
  }, [symbol, interval]);

  const analyze = async () => {
    setAnalyzing(true);
    try {
      setAnalysis(await api.analyzeBacktest(symbol, interval));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setAnalyzing(false);
    }
  };

  const m = result?.metrics ?? null;
  const da = m?.directional_accuracy ?? null;
  const daTone = da == null ? undefined : da >= 60 ? "good" : da <= 50 ? "bad" : "warn";
  const skill = m?.skill_vs_naive ?? null;

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="flex max-h-[88vh] w-full max-w-3xl flex-col rounded-xl border border-border bg-surface shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border p-3">
          <h2 className="text-sm font-semibold">
            Beam backtest · {symbol} · {interval}
          </h2>
          <span className="text-[11px] text-text-muted">
            walk-forward · predict next from prior history
          </span>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          {error && <p className="text-sm text-bad">{error}</p>}

          {!result && !error && (
            <div className="flex items-center gap-2 py-10 text-sm text-text-muted">
              <Spinner className="text-accent" /> Running walk-forward backtest…
            </div>
          )}

          {result && !m && (
            <p className="py-10 text-center text-sm text-text-muted">
              {result.note ?? "Not enough history to backtest."}
            </p>
          )}

          {result && m && (
            <>
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
                <Stat
                  label="Direction"
                  value={da == null ? "—" : `${da.toFixed(0)}%`}
                  tone={daTone}
                />
                <Stat
                  label="Skill vs naive"
                  value={skill == null ? "—" : skill.toFixed(3)}
                  tone={skill == null ? undefined : skill > 0 ? "good" : "bad"}
                />
                <Stat label="MAPE" value={m.mape == null ? "—" : `${m.mape.toFixed(2)}%`} />
                <Stat label="MAE" value={m.mae.toFixed(2)} />
                <Stat label="RMSE" value={m.rmse.toFixed(2)} />
                <Stat label="Steps" value={String(m.n)} />
              </div>

              <div>
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                    Actual vs predicted price
                  </span>
                  <span className="flex items-center gap-3 text-[11px] text-text-muted">
                    <span className="flex items-center gap-1">
                      <span className="h-0.5 w-4 bg-text" /> actual
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="h-0 w-4 border-t-2 border-dashed border-accent" />{" "}
                      predicted
                    </span>
                  </span>
                </div>
                <div className="h-64 rounded-lg border border-border bg-surface p-2">
                  <BacktestChart points={result.points} />
                </div>
                <p className="mt-1.5 text-[11px] leading-relaxed text-text-muted">
                  Directional accuracy is the share of steps where the projected
                  move (vs the prior close) matched reality — 50% is a coin flip,
                  and the goal is to clear 60%. Skill above 0 means the beam beats
                  a naive “tomorrow = today” baseline.
                </p>
              </div>

              {!analysis && (
                <button
                  onClick={analyze}
                  disabled={analyzing}
                  className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-60"
                >
                  {analyzing ? (
                    <>
                      <Spinner /> Analyzing beam
                    </>
                  ) : (
                    "Analyze beam with LLM"
                  )}
                </button>
              )}

              {analysis && (
                <div className="space-y-3 rounded-lg border border-border bg-surface-2 p-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                      Beam analysis
                    </span>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                        analysis.analysis.verdict === "signal"
                          ? "bg-good/15 text-good"
                          : analysis.analysis.verdict === "no_signal"
                            ? "bg-bad/15 text-bad"
                            : "bg-surface-3 text-text-muted"
                      }`}
                    >
                      {VERDICT_LABEL[analysis.analysis.verdict]}
                    </span>
                  </div>
                  <p className="text-sm leading-relaxed text-text">
                    {analysis.analysis.assessment}
                  </p>

                  {analysis.analysis.beam_weaknesses.length > 0 && (
                    <div>
                      <h4 className="mb-1 text-[11px] font-semibold text-text-muted">
                        Weaknesses
                      </h4>
                      <ul className="list-disc space-y-0.5 pl-4 text-xs text-text-muted">
                        {analysis.analysis.beam_weaknesses.map((w, i) => (
                          <li key={i}>{w}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {analysis.analysis.improvements.length > 0 && (
                    <div>
                      <h4 className="mb-1 text-[11px] font-semibold text-text-muted">
                        Improvements
                      </h4>
                      <ul className="flex flex-col gap-1.5">
                        {analysis.analysis.improvements.map((imp, i) => (
                          <li
                            key={i}
                            className="rounded-md border border-border bg-surface p-2"
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-xs font-medium text-text">
                                {imp.idea}
                              </span>
                              <span
                                className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                                  IMPACT_TONE[imp.expected_impact]
                                }`}
                              >
                                {imp.expected_impact}
                              </span>
                            </div>
                            <p className="mt-0.5 text-[11px] leading-relaxed text-text-muted">
                              {imp.rationale}
                            </p>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {!analysis.llm_available && (
                    <p className="text-[11px] text-text-muted">
                      Set ANTHROPIC_API_KEY for a full LLM critique.
                    </p>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex justify-end border-t border-border p-3">
          <button
            onClick={onClose}
            className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-xs font-medium text-text-muted hover:text-text"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
