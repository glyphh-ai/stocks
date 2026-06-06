"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import type {
  Metric,
  PathInfo,
  PredictionResponse,
  SeriesResponse,
  SymbolInfo,
  Trade,
} from "@/lib/types";
import { colorForPath, shortLabel } from "@/lib/colors";
import { TrendChart, type TradeMarker } from "./TrendChart";
import { SeriesPicker } from "./SeriesPicker";
import { TradesButton } from "./TradesPanel";
import { PredictionModal } from "./PredictionModal";
import { ClearHistoryButton } from "./ClearHistoryButton";
import { Spinner } from "../Spinner";

const LONG_COLOR = "#16a34a";
const SHORT_COLOR = "#dc2626";

const METRICS: { id: Metric; label: string; hint: string }[] = [
  { id: "baseline", label: "Drift vs base", hint: "Cosine distance from the first version" },
  { id: "delta", label: "Step drift", hint: "Distance from the previous version" },
  { id: "value", label: "Raw value", hint: "Scalar role value (roles only)" },
];

const REFRESH_MS = 15_000;

const DEFAULT_METRIC: Metric = "baseline";
const DEFAULT_SELECTION = ["cortex"];

export function Dashboard() {
  const { data: symbols, mutate: mutateSymbols } = useSWR<SymbolInfo[]>(
    "/symbols",
    () => api.symbols(),
    { refreshInterval: REFRESH_MS },
  );

  const [symbol, setSymbol] = useState<string>("");
  const [interval, setInterval] = useState<string>("1m");
  const [metric, setMetric] = useState<Metric>(DEFAULT_METRIC);
  const [selected, setSelected] = useState<Set<string>>(new Set(DEFAULT_SELECTION));

  const [seedSymbol, setSeedSymbol] = useState<string>("");
  const [seeding, setSeeding] = useState(false);
  const [seedError, setSeedError] = useState<string | null>(null);

  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const [predicting, setPredicting] = useState(false);
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null);

  const resetView = () => {
    setMetric(DEFAULT_METRIC);
    setSelected(new Set(DEFAULT_SELECTION));
  };

  const seed = async () => {
    const sym = seedSymbol.trim().toUpperCase();
    if (!sym) return;
    setSeeding(true);
    setSeedError(null);
    try {
      await api.backfill(sym, "6mo", "1d");
      setSeedSymbol("");
      await mutateSymbols();
      setSymbol(sym);
      setInterval("1d");
      resetView();
    } catch (e) {
      setSeedError(e instanceof Error ? e.message : "Backfill failed");
    } finally {
      setSeeding(false);
    }
  };

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

  const { data: seriesData, mutate: mutateSeries } = useSWR<SeriesResponse>(
    seriesKey,
    () => api.series(symbol, interval, metric, selectedPaths),
    { refreshInterval: REFRESH_MS, keepPreviousData: true },
  );

  const runNow = async () => {
    if (!symbol) return;
    setRunning(true);
    setRunError(null);
    try {
      await api.run(symbol, interval);
      await Promise.all([mutateSymbols(), mutateSeries()]);
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Run failed");
    } finally {
      setRunning(false);
    }
  };

  const predict = async () => {
    if (!symbol) return;
    setPredicting(true);
    try {
      setPrediction(await api.predict(symbol, interval));
    } finally {
      setPredicting(false);
    }
  };

  const { data: trades, mutate: mutateTrades } = useSWR<Trade[]>(
    symbol ? `/trades?${symbol}` : null,
    () => api.trades(symbol),
  );

  const onHistoryCleared = async () => {
    await Promise.all([mutateSymbols(), mutateSeries(), mutateTrades()]);
    resetView();
  };

  const tradeMarkers = useMemo<TradeMarker[]>(() => {
    const out: TradeMarker[] = [];
    for (const t of trades ?? []) {
      const sec = (ts: string) => Math.floor(new Date(ts).getTime() / 1000);
      out.push({
        time: sec(t.entry_ts) as TradeMarker["time"],
        position: t.side === "long" ? "belowBar" : "aboveBar",
        shape: t.side === "long" ? "arrowUp" : "arrowDown",
        color: t.side === "long" ? LONG_COLOR : SHORT_COLOR,
        text: `${t.side === "long" ? "L" : "S"} ${t.entry_price}`,
      });
      if (t.status === "closed" && t.exit_ts != null) {
        out.push({
          time: sec(t.exit_ts) as TradeMarker["time"],
          position: t.side === "long" ? "aboveBar" : "belowBar",
          shape: t.side === "long" ? "arrowDown" : "arrowUp",
          color: (t.pnl ?? 0) >= 0 ? LONG_COLOR : SHORT_COLOR,
          text: `exit ${t.exit_price}`,
        });
      }
    }
    return out.sort((a, b) => (a.time as number) - (b.time as number));
  }, [trades]);

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
                  interval === iv ? "bg-accent text-accent-fg" : "bg-surface-2 text-text-muted hover:text-text"
                }`}
              >
                {iv}
              </button>
            ))}
          </div>

          <div className="mt-3 border-t border-border pt-3">
            <label className="mb-1 block px-1 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
              Seed history
            </label>
            <div className="flex gap-1.5">
              <input
                value={seedSymbol}
                onChange={(e) => setSeedSymbol(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && seed()}
                placeholder="ticker, e.g. NVDA"
                spellCheck={false}
                className="min-w-0 flex-1 rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-sm uppercase outline-none focus:border-accent"
              />
              <button
                onClick={seed}
                disabled={seeding || seedSymbol.trim() === ""}
                title="Pull 6 months of daily history"
                className="shrink-0 rounded-lg bg-accent px-2.5 py-1.5 text-xs font-semibold text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                {seeding ? "…" : "Seed"}
              </button>
            </div>
            {seedError && <p className="mt-1 px-1 text-xs text-bad">{seedError}</p>}
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

          <div className="flex items-center gap-2">
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
            <TradesButton symbol={symbol} interval={interval} onChanged={() => mutateTrades()} />
            <button
              onClick={predict}
              disabled={!symbol || predicting}
              title="Beam-search the next projected glyph from recorded history"
              className="rounded-lg border border-border bg-surface-2 px-2.5 py-1 text-xs font-medium text-text-muted transition-colors hover:text-text disabled:opacity-40"
            >
              {predicting ? (
                <span className="flex items-center gap-1.5">
                  <Spinner className="text-accent" /> Projecting
                </span>
              ) : (
                "Predict"
              )}
            </button>
            <button
              onClick={runNow}
              disabled={!symbol || running}
              title="Run the glyph job now and append a live version"
              className="rounded-lg bg-accent px-2.5 py-1 text-xs font-semibold text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              {running ? (
                <span className="flex items-center gap-1.5">
                  <Spinner /> Running
                </span>
              ) : (
                "Run now"
              )}
            </button>
            <button
              onClick={resetView}
              title="Reset metric and selection to defaults"
              className="rounded-lg border border-border bg-surface-2 px-2.5 py-1 text-xs font-medium text-text-muted transition-colors hover:text-text"
            >
              Reset view
            </button>
            <ClearHistoryButton
              symbol={symbol}
              interval={interval}
              onCleared={onHistoryCleared}
            />
          </div>
        </div>
        {runError && (
          <div className="shrink-0 border-b border-border bg-bad/10 px-4 py-1.5 text-xs text-bad">
            {runError}
          </div>
        )}

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
            <TrendChart series={seriesData?.series ?? []} markers={tradeMarkers} />
          ) : (
            <div className="grid h-full place-items-center text-sm text-text-muted">
              {symbol ? "Select a role, segment, layer, or the cortex to chart." : "No stocks configured yet."}
            </div>
          )}
        </div>
      </section>

      {prediction && (
        <PredictionModal data={prediction} onClose={() => setPrediction(null)} />
      )}
    </div>
  );
}
