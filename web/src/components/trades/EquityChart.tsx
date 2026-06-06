"use client";

import { useEffect, useRef } from "react";
import {
  AreaSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { useTheme } from "next-themes";

function cssVar(name: string): string {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export interface EquityPoint {
  time: number; // unix seconds
  value: number; // cumulative net P&L
}

/** Cumulative net-P&L equity curve. Green when ending in profit, red in loss. */
export function EquityChart({ points }: { points: EquityPoint[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const { resolvedTheme } = useTheme();

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
        vertLine: { color: cssVar("--border-strong"), style: LineStyle.Dotted },
        horzLine: { color: cssVar("--border-strong"), style: LineStyle.Dotted },
      },
      rightPriceScale: { borderColor: cssVar("--border") },
      timeScale: { borderColor: cssVar("--border"), timeVisible: false },
    });
    const series = chart.addSeries(AreaSeries, {
      lineWidth: 2,
      priceLineVisible: false,
    });
    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.applyOptions({
      layout: { textColor: cssVar("--text-muted") },
      grid: {
        vertLines: { color: cssVar("--grid") },
        horzLines: { color: cssVar("--grid") },
      },
      rightPriceScale: { borderColor: cssVar("--border") },
      timeScale: { borderColor: cssVar("--border") },
    });
  }, [resolvedTheme]);

  useEffect(() => {
    const series = seriesRef.current;
    const chart = chartRef.current;
    if (!series || !chart) return;
    const end = points.length ? points[points.length - 1].value : 0;
    const up = end >= 0;
    const color = up ? cssVar("--good") : cssVar("--bad");
    series.applyOptions({
      lineColor: color,
      topColor: up ? "rgba(22,163,74,0.28)" : "rgba(220,38,38,0.28)",
      bottomColor: "transparent",
    });
    series.setData(
      points.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })),
    );
    chart.timeScale().fitContent();
  }, [points, resolvedTheme]);

  return <div ref={containerRef} className="h-full w-full" />;
}
