"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  CrosshairMode,
  LineSeries,
  LineStyle,
  createChart,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { useTheme } from "next-themes";
import type { BacktestPoint } from "@/lib/types";

function cssVar(name: string): string {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Actual price (solid) vs the beam's projected next price (dashed). */
export function BacktestChart({ points }: { points: BacktestPoint[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
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
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: cssVar("--border") },
      timeScale: { borderColor: cssVar("--border"), timeVisible: false },
    });
    chartRef.current = chart;

    const data = [...points].sort(
      (a, b) => +new Date(a.ts) - +new Date(b.ts),
    );
    const toSec = (ts: string) =>
      Math.floor(new Date(ts).getTime() / 1000) as UTCTimestamp;

    const actual = chart.addSeries(LineSeries, {
      color: cssVar("--text"),
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    actual.setData(data.map((p) => ({ time: toSec(p.ts), value: p.actual })));

    const predicted = chart.addSeries(LineSeries, {
      color: cssVar("--accent"),
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    predicted.setData(
      data.map((p) => ({ time: toSec(p.ts), value: p.predicted })),
    );

    chart.timeScale().fitContent();
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [points, resolvedTheme]);

  return <div ref={containerRef} className="h-full w-full" />;
}
