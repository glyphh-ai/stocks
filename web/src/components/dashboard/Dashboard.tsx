"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import type {
  Metric,
  PathInfo,
  PredictionResponse,
  PredictionSeriesResponse,
  Series,
  SeriesResponse,
  SymbolInfo,
  Trade,
} from "@/lib/types";
import { colorForPath, shortLabel } from "@/lib/colors";

const PRED_PREFIX = "pred:";
const PRED_AHEAD_PREFIX = "predahead:";
const PRED_COLOR = "#16a34a";
import { TrendChart, type TradeMarker } from "./TrendChart";
import { SeriesPicker } from "./SeriesPicker";
import { TradesButton } from "./TradesPanel";
import { PredictionModal } from "./PredictionModal";
import { BacktestModal } from "./BacktestModal";
import { ClearHistoryButton } from "./ClearHistoryButton";
import { Spinner } from "../Spinner";

const LONG_COLOR = "#16a34a";
const SHORT_COLOR = "#dc2626";

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="11"
      height="11"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`transition-transform ${open ? "rotate-90" : ""}`}
    >
      <path d="M9 6l6 6-6 6" />
    </svg>
  );
}

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
  const [actualOpen, setActualOpen] = useState(true);
  const [predOpen, setPredOpen] = useState(true);

  const [seedSymbol, setSeedSymbol] = useState<string>("");
  const [seeding, setSeeding] = useState(false);
  const [seedError, setSeedError] = useState<string | null>(null);
  const [seedProgress, setSeedProgress] = useState<{ done: number; total: number } | null>(null);

  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const [predicting, setPredicting] = useState(false);
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null);
  const [backtesting, setBacktesting] = useState(false);

  const { mutate: globalMutate } = useSWRConfig();

  const resetView = () => {
    setMetric(DEFAULT_METRIC);
    setSelected(new Set(DEFAULT_SELECTION));
  };

  // Seed = wipe and rebuild a ticker's full history tick by tick: each bar runs
  // the entire config point-in-time (price, commodities, macro, GDELT news) and
  // its walk-forward prediction. We select the symbol up front and revalidate as
  // bars stream so the chart visibly fills in. Progress shows under the input.
  const seed = async () => {
    const sym = seedSymbol.trim().toUpperCase();
    if (!sym || seeding) return;
    setSeeding(true);
    setSeedError(null);
    setSeedProgress({ done: 0, total: 0 });
    setSymbol(sym);
    setInterval("1d");
    setSelected(new Set(["cortex"]));
    const refresh = () =>
      globalMutate((key) => typeof key === "string" && key.includes(sym));
    try {
      await api.replay(sym, "1d", { range: "6mo", withLlmAhead: true }, (e) => {
        if (e.event === "reset") {
          setSeedProgress({ done: 0, total: e.bars });
        } else if (e.event === "bar") {
          setSeedProgress({ done: e.index + 1, total: e.total });
          if ((e.index + 1) % 5 === 0) refresh();
        } else if (e.event === "prediction" && e.rows % 5 === 0) {
          refresh();
        }
      });
      setSeedSymbol("");
      await mutateSymbols();
      await refresh();
      resetView();
    } catch (e) {
      setSeedError(e instanceof Error ? e.message : "Seed failed");
    } finally {
      setSeeding(false);
      setSeedProgress(null);
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
  // Selection holds both actual paths and "pred:"-prefixed prediction paths.
  const actualPaths = useMemo(
    () => selectedPaths.filter((p) => !p.startsWith(PRED_PREFIX)),
    [selectedPaths],
  );
  const predPaths = useMemo(
    () => selectedPaths.filter((p) => p.startsWith(PRED_PREFIX)).map((p) => p.slice(PRED_PREFIX.length)),
    [selectedPaths],
  );

  const seriesKey = symbol && actualPaths.length
    ? `/series?${symbol}&${interval}&${metric}&${actualPaths.join(",")}`
    : null;

  const { data: seriesData, mutate: mutateSeries } = useSWR<SeriesResponse>(
    seriesKey,
    () => api.series(symbol, interval, metric, actualPaths),
    { refreshInterval: REFRESH_MS, keepPreviousData: true },
  );

  const { data: predPathInfos, mutate: mutatePredPaths } = useSWR<PathInfo[]>(
    symbol ? `/predict/next/paths?${symbol}&${interval}` : null,
    () => api.predictionPaths(symbol, interval),
  );

  const predSeriesKey = symbol && predPaths.length
    ? `/predict/next/series?${symbol}&${interval}&${predPaths.join(",")}`
    : null;

  const { data: predSeriesData, mutate: mutatePredSeries } =
    useSWR<PredictionSeriesResponse>(
      predSeriesKey,
      () => api.predictionSeries(symbol, interval, predPaths),
      { refreshInterval: REFRESH_MS, keepPreviousData: true },
    );

  const [predRefreshing, setPredRefreshing] = useState(false);

  // Predicted signal lines: the walk-forward history draws green-solid
  // ("pred:"), and the one-step-ahead step draws green-dashed ("predahead:")
  // as a short segment from the last history projection to the ahead point.
  const chartSeries = useMemo<Series[]>(() => {
    const actual = seriesData?.series ?? [];
    const predicted: Series[] = [];
    for (const s of predSeriesData?.series ?? []) {
      predicted.push({
        path: `${PRED_PREFIX}${s.path}`,
        metric: "value" as Metric,
        points: s.points,
      });
      if (s.ahead && s.points.length) {
        predicted.push({
          path: `${PRED_AHEAD_PREFIX}${s.path}`,
          metric: "value" as Metric,
          points: [s.points[s.points.length - 1], s.ahead],
        });
      }
    }
    return [...actual, ...predicted];
  }, [seriesData, predSeriesData]);

  const runNow = async () => {
    if (!symbol) return;
    setRunning(true);
    setRunError(null);
    try {
      await api.run(symbol, interval);
      await Promise.all([mutateSymbols(), mutateSeries()]);
      // A new actual version printed — re-project with the full ensemble (LLM).
      setPredRefreshing(true);
      await api.refreshPredictions(symbol, interval, true).catch(() => {});
      await Promise.all([mutatePredPaths(), mutatePredSeries()]);
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Run failed");
    } finally {
      setRunning(false);
      setPredRefreshing(false);
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
    // Predictions are derived from history — rebuild (or clear) them too.
    await api.refreshPredictions(symbol, interval, false).catch(() => {});
    await Promise.all([
      mutateSymbols(),
      mutateSeries(),
      mutateTrades(),
      mutatePredPaths(),
      mutatePredSeries(),
    ]);
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
                disabled={seeding}
                className="min-w-0 flex-1 rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-sm uppercase outline-none focus:border-accent disabled:opacity-50"
              />
              <button
                onClick={seed}
                disabled={seeding || seedSymbol.trim() === ""}
                title="Wipe and rebuild 6 months of daily history, running the full config (price, commodities, macro, news) point-in-time for every bar"
                className="flex shrink-0 items-center gap-1.5 rounded-lg bg-accent px-2.5 py-1.5 text-xs font-semibold text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                {seeding ? <Spinner /> : "Seed"}
              </button>
            </div>
            {seeding && seedProgress && (
              <div className="mt-2 px-1">
                <div className="flex items-center justify-between text-[11px] text-text-muted">
                  <span>
                    {seedProgress.total
                      ? `Building ${seedProgress.done}/${seedProgress.total} bars…`
                      : "Resetting…"}
                  </span>
                  {seedProgress.total > 0 && (
                    <span>{Math.round((seedProgress.done / seedProgress.total) * 100)}%</span>
                  )}
                </div>
                <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-surface-3">
                  <div
                    className="h-full rounded-full bg-accent transition-all"
                    style={{
                      width: seedProgress.total
                        ? `${(seedProgress.done / seedProgress.total) * 100}%`
                        : "0%",
                    }}
                  />
                </div>
              </div>
            )}
            {seedError && <p className="mt-1 px-1 text-xs text-bad">{seedError}</p>}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <button
            onClick={() => setActualOpen((o) => !o)}
            className="mb-1.5 flex w-full items-center gap-1 px-1 text-[11px] font-semibold uppercase tracking-wider text-text-muted hover:text-text"
          >
            <Chevron open={actualOpen} />
            Actual
          </button>
          {actualOpen &&
            (paths?.length ? (
              <SeriesPicker paths={paths} selected={selected} onToggle={toggle} />
            ) : (
              <p className="px-1 text-sm text-text-muted">No nodes yet.</p>
            ))}

          <div className="mt-4 border-t border-border pt-3">
            <div className="mb-1.5 flex items-center justify-between px-1">
              <button
                onClick={() => setPredOpen((o) => !o)}
                className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted hover:text-text"
              >
                <Chevron open={predOpen} />
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: PRED_COLOR }}
                />
                Prediction
              </button>
              {predRefreshing && <Spinner className="text-good" />}
            </div>
            {predOpen &&
              (predPathInfos?.length ? (
                <SeriesPicker
                  paths={predPathInfos}
                  selected={selected}
                  onToggle={toggle}
                  keyPrefix={PRED_PREFIX}
                  color={() => PRED_COLOR}
                />
              ) : (
                <p className="px-1 text-xs text-text-muted">
                  {predRefreshing ? "Projecting next interval…" : "No prediction yet."}
                </p>
              ))}
          </div>
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
              onClick={() => setBacktesting(true)}
              disabled={!symbol}
              title="Walk the chart history, predicting each next interval, to score the beam"
              className="rounded-lg border border-border bg-surface-2 px-2.5 py-1 text-xs font-medium text-text-muted transition-colors hover:text-text disabled:opacity-40"
            >
              Backtest
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
            {selectedPaths.map((p) => {
              const isPred = p.startsWith(PRED_PREFIX);
              const raw = isPred ? p.slice(PRED_PREFIX.length) : p;
              return (
                <span key={p} className="flex items-center gap-1.5 text-xs">
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: isPred ? PRED_COLOR : colorForPath(raw) }}
                  />
                  <span className="text-text-muted">
                    {shortLabel(raw)}
                    {isPred && " (pred)"}
                  </span>
                </span>
              );
            })}
          </div>
        )}

        <div className="relative min-h-0 flex-1 p-2">
          {symbol && selectedPaths.length > 0 ? (
            <TrendChart series={chartSeries} markers={tradeMarkers} />
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
      {backtesting && symbol && (
        <BacktestModal
          symbol={symbol}
          interval={interval}
          onClose={() => setBacktesting(false)}
        />
      )}
    </div>
  );
}
