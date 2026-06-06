"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { Metric, PathInfo, SeriesResponse, SymbolInfo } from "@/lib/types";
import { colorForPath, shortLabel } from "@/lib/colors";
import { TrendChart } from "./TrendChart";
import { SeriesPicker } from "./SeriesPicker";

const METRICS: { id: Metric; label: string; hint: string }[] = [
  { id: "baseline", label: "Drift vs base", hint: "Cosine distance from the first version" },
  { id: "delta", label: "Step drift", hint: "Distance from the previous version" },
  { id: "value", label: "Raw value", hint: "Scalar role value (roles only)" },
];

const REFRESH_MS = 15_000;

export function Dashboard() {
  const { data: symbols } = useSWR<SymbolInfo[]>("/symbols", () => api.symbols(), {
    refreshInterval: REFRESH_MS,
  });

  const [symbol, setSymbol] = useState<string>("");
  const [interval, setInterval] = useState<string>("1m");
  const [metric, setMetric] = useState<Metric>("baseline");
  const [selected, setSelected] = useState<Set<string>>(new Set(["cortex"]));

  // Default to the first symbol once data arrives.
  useEffect(() => {
    if (!symbol && symbols?.length) {
      setSymbol(symbols[0].symbol);
      setInterval(symbols[0].interval);
    }
  }, [symbols, symbol]);

  const intervals = useMemo(
    () => [...new Set((symbols ?? []).filter((s) => s.symbol === symbol).map((s) => s.interval))],
    [symbols, symbol],
  );

  // Keep the interval valid for the selected symbol (symbols don't share intervals).
  useEffect(() => {
    if (intervals.length && !intervals.includes(interval)) setInterval(intervals[0]);
  }, [intervals, interval]);

  const { data: paths } = useSWR<PathInfo[]>(
    symbol ? `/paths?${symbol}&${interval}` : null,
    () => api.paths(symbol, interval),
  );

  const selectedPaths = useMemo(() => [...selected], [selected]);
  const seriesKey = symbol
    ? `/series?${symbol}&${interval}&${metric}&${selectedPaths.join(",")}`
    : null;

  const { data: seriesData } = useSWR<SeriesResponse>(
    seriesKey,
    () => api.series(symbol, interval, metric, selectedPaths),
    { refreshInterval: REFRESH_MS, keepPreviousData: true },
  );

  const toggle = (path: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });

  const activeInfo = symbols?.find((s) => s.symbol === symbol && s.interval === interval);

  return (
    <div className="flex h-full min-h-0">
      {/* Left rail: stock + series selection */}
      <aside className="flex w-64 shrink-0 flex-col border-r border-border bg-surface">
        <div className="border-b border-border p-3">
          <label className="mb-1 block px-1 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
            Stock
          </label>
          <select
            value={symbol}
            onChange={(e) => {
              setSymbol(e.target.value);
              setSelected(new Set(["cortex"]));
            }}
            className="w-full rounded-lg border border-border bg-surface-2 px-2.5 py-2 text-sm font-medium outline-none focus:border-accent"
          >
            {!symbols?.length && <option>— no data —</option>}
            {[...new Set((symbols ?? []).map((s) => s.symbol))].map((sym) => (
              <option key={sym} value={sym}>
                {sym}
              </option>
            ))}
          </select>

          <div className="mt-2 flex flex-wrap gap-1">
            {intervals.map((iv) => (
              <button
                key={iv}
                onClick={() => setInterval(iv)}
                className={`rounded-md px-2 py-1 text-xs font-medium transition-colors ${
                  interval === iv ? "bg-accent text-white" : "bg-surface-2 text-text-muted hover:text-text"
                }`}
              >
                {iv}
              </button>
            ))}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {paths?.length ? (
            <SeriesPicker paths={paths} selected={selected} onToggle={toggle} />
          ) : (
            <p className="px-1 text-sm text-text-muted">No nodes yet.</p>
          )}
        </div>
      </aside>

      {/* Main chart */}
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-2.5">
          <div className="flex items-baseline gap-3">
            <h1 className="text-lg font-semibold tracking-tight">{symbol || "—"}</h1>
            {activeInfo && (
              <span className="text-xs text-text-muted">
                {activeInfo.versions} versions · {interval}
              </span>
            )}
            <span className="flex items-center gap-1.5 text-xs text-good">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-good" />
              live
            </span>
          </div>

          <div className="flex rounded-lg border border-border bg-surface-2 p-0.5">
            {METRICS.map((m) => (
              <button
                key={m.id}
                title={m.hint}
                onClick={() => setMetric(m.id)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  metric === m.id ? "bg-surface text-text shadow-sm" : "text-text-muted hover:text-text"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {/* Legend */}
        {selectedPaths.length > 0 && (
          <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-b border-border px-4 py-2">
            {selectedPaths.map((p) => (
              <span key={p} className="flex items-center gap-1.5 text-xs">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: colorForPath(p) }} />
                <span className="text-text-muted">{shortLabel(p)}</span>
              </span>
            ))}
          </div>
        )}

        <div className="relative min-h-0 flex-1 p-2">
          {symbol && selectedPaths.length > 0 ? (
            <TrendChart series={seriesData?.series ?? []} />
          ) : (
            <div className="grid h-full place-items-center text-sm text-text-muted">
              {symbol ? "Select a role, segment, layer, or the cortex to chart." : "No stocks configured yet."}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
