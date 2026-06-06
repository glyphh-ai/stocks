"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  CrosshairMode,
  LineSeries,
  LineStyle,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { useTheme } from "next-themes";
import type { Series } from "@/lib/types";
import { colorForPath } from "@/lib/colors";

function cssVar(name: string): string {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function toData(points: Series["points"]) {
  const seen = new Map<number, number>();
  for (const p of points) {
    if (p.v == null) continue;
    const t = Math.floor(new Date(p.t).getTime() / 1000);
    seen.set(t, p.v); // last write wins on duplicate seconds
  }
  return [...seen.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([time, value]) => ({ time: time as UTCTimestamp, value }));
}

export function TrendChart({ series }: { series: Series[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesMap = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const { resolvedTheme } = useTheme();

  // Create the chart once.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: cssVar("--text-muted"),
        fontFamily: "var(--font-geist-sans), system-ui, sans-serif",
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: cssVar("--grid") },
        horzLines: { color: cssVar("--grid") },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: cssVar("--border-strong"), labelBackgroundColor: cssVar("--accent"), style: LineStyle.Dotted },
        horzLine: { color: cssVar("--border-strong"), labelBackgroundColor: cssVar("--accent"), style: LineStyle.Dotted },
      },
      rightPriceScale: { borderColor: cssVar("--border") },
      timeScale: { borderColor: cssVar("--border"), timeVisible: true, secondsVisible: false },
    });
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesMap.current.clear();
    };
  }, []);

  // Re-theme when the color scheme flips.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.applyOptions({
      layout: { textColor: cssVar("--text-muted") },
      grid: { vertLines: { color: cssVar("--grid") }, horzLines: { color: cssVar("--grid") } },
      rightPriceScale: { borderColor: cssVar("--border") },
      timeScale: { borderColor: cssVar("--border") },
      crosshair: {
        vertLine: { color: cssVar("--border-strong"), labelBackgroundColor: cssVar("--accent") },
        horzLine: { color: cssVar("--border-strong"), labelBackgroundColor: cssVar("--accent") },
      },
    });
  }, [resolvedTheme]);

  // Sync series with selection + data.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const wanted = new Set(series.map((s) => s.path));

    for (const [path, s] of seriesMap.current) {
      if (!wanted.has(path)) {
        chart.removeSeries(s);
        seriesMap.current.delete(path);
      }
    }

    for (const s of series) {
      let line = seriesMap.current.get(s.path);
      if (!line) {
        line = chart.addSeries(LineSeries, {
          color: colorForPath(s.path),
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: true,
          crosshairMarkerRadius: 3,
        });
        seriesMap.current.set(s.path, line);
      }
      line.setData(toData(s.points));
    }
  }, [series]);

  return <div ref={containerRef} className="h-full w-full" />;
}
