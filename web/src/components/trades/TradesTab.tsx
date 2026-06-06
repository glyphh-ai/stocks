"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { Trade } from "@/lib/types";
import { EquityChart, type EquityPoint } from "./EquityChart";

function money(n: number): string {
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(n).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function fmtDate(ts: string | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleDateString(undefined, {
    year: "2-digit",
    month: "short",
    day: "numeric",
  });
}

function pnlClass(n: number | null): string {
  if (n == null) return "text-text-muted";
  return n >= 0 ? "text-good" : "text-bad";
}

type StatusFilter = "all" | "open" | "closed";
type SideFilter = "all" | "long" | "short";

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "good" | "bad" | "muted";
}) {
  const color =
    tone === "good" ? "text-good" : tone === "bad" ? "text-bad" : "text-text";
  return (
    <div className="rounded-xl border border-border bg-surface p-3">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        {label}
      </div>
      <div className={`mt-1 text-lg font-semibold tabular-nums ${color}`}>
        {value}
      </div>
    </div>
  );
}

export function TradesTab() {
  const { data: trades } = useSWR<Trade[]>("/trades-all", () => api.trades());

  const [symbol, setSymbol] = useState("all");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [side, setSide] = useState<SideFilter>("all");

  const symbols = useMemo(
    () => [...new Set((trades ?? []).map((t) => t.symbol))].sort(),
    [trades],
  );

  const filtered = useMemo(() => {
    return (trades ?? []).filter((t) => {
      if (symbol !== "all" && t.symbol !== symbol) return false;
      if (status !== "all" && t.status !== status) return false;
      if (side !== "all" && t.side !== side) return false;
      return true;
    });
  }, [trades, symbol, status, side]);

  const closed = useMemo(
    () => filtered.filter((t) => t.status === "closed"),
    [filtered],
  );

  const stats = useMemo(() => {
    const net = closed.reduce((a, t) => a + (t.net_pnl ?? 0), 0);
    const gross = closed.reduce((a, t) => a + (t.pnl ?? 0), 0);
    const fees = closed.reduce((a, t) => a + t.entry_fee + t.exit_fee, 0);
    const wins = closed.filter((t) => (t.net_pnl ?? 0) >= 0).length;
    const openCount = filtered.filter((t) => t.status === "open").length;
    return {
      net,
      gross,
      fees,
      winRate: closed.length ? (wins / closed.length) * 100 : 0,
      closedCount: closed.length,
      openCount,
    };
  }, [closed, filtered]);

  const equity = useMemo<EquityPoint[]>(() => {
    const sorted = [...closed]
      .filter((t) => t.exit_ts)
      .sort((a, b) => +new Date(a.exit_ts!) - +new Date(b.exit_ts!));
    let cum = 0;
    return sorted.map((t) => {
      cum += t.net_pnl ?? 0;
      return { time: Math.floor(new Date(t.exit_ts!).getTime() / 1000), value: cum };
    });
  }, [closed]);

  const rows = useMemo(
    () =>
      [...filtered].sort(
        (a, b) => +new Date(b.entry_ts) - +new Date(a.entry_ts),
      ),
    [filtered],
  );

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold tracking-tight">Trade history</h1>
        <div className="flex items-center gap-2 text-xs">
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="rounded-lg border border-border bg-surface-2 px-2 py-1 outline-none focus:border-accent"
          >
            <option value="all">All symbols</option>
            {symbols.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as StatusFilter)}
            className="rounded-lg border border-border bg-surface-2 px-2 py-1 outline-none focus:border-accent"
          >
            <option value="all">All status</option>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
          </select>
          <select
            value={side}
            onChange={(e) => setSide(e.target.value as SideFilter)}
            className="rounded-lg border border-border bg-surface-2 px-2 py-1 outline-none focus:border-accent"
          >
            <option value="all">Long &amp; short</option>
            <option value="long">Long</option>
            <option value="short">Short</option>
          </select>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Metric
          label="Net P&L"
          value={money(stats.net)}
          tone={stats.net >= 0 ? "good" : "bad"}
        />
        <Metric label="Gross P&L" value={money(stats.gross)} />
        <Metric label="Fees" value={money(stats.fees)} tone="muted" />
        <Metric label="Win rate" value={`${stats.winRate.toFixed(0)}%`} />
        <Metric label="Closed" value={String(stats.closedCount)} />
        <Metric label="Open" value={String(stats.openCount)} />
      </div>

      {/* Equity curve */}
      <div className="rounded-xl border border-border bg-surface p-3">
        <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
          Cumulative net P&L
        </div>
        <div className="h-56">
          {equity.length > 0 ? (
            <EquityChart points={equity} />
          ) : (
            <div className="grid h-full place-items-center text-sm text-text-muted">
              No closed trades in this filter.
            </div>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-border bg-surface">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-text-muted">
              <th className="px-3 py-2 font-semibold">Symbol</th>
              <th className="px-3 py-2 font-semibold">Side</th>
              <th className="px-3 py-2 text-right font-semibold">Vol</th>
              <th className="px-3 py-2 text-right font-semibold">Entry</th>
              <th className="px-3 py-2 text-right font-semibold">Exit</th>
              <th className="px-3 py-2 text-right font-semibold">Gross</th>
              <th className="px-3 py-2 text-right font-semibold">Fees</th>
              <th className="px-3 py-2 text-right font-semibold">Net</th>
              <th className="px-3 py-2 text-right font-semibold">Date</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-3 py-8 text-center text-text-muted">
                  No trades match this filter.
                </td>
              </tr>
            ) : (
              rows.map((t) => (
                <tr
                  key={t.id}
                  className="border-b border-border/60 last:border-0 hover:bg-surface-2"
                >
                  <td className="px-3 py-2 font-medium">{t.symbol}</td>
                  <td className="px-3 py-2">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                        t.side === "long"
                          ? "bg-good/15 text-good"
                          : "bg-bad/15 text-bad"
                      }`}
                    >
                      {t.side}
                    </span>
                    {t.status === "open" && (
                      <span className="ml-1.5 text-[10px] uppercase text-text-muted">
                        open
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{t.volume}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    ${t.entry_price.toFixed(2)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {t.exit_price != null ? `$${t.exit_price.toFixed(2)}` : "—"}
                  </td>
                  <td
                    className={`px-3 py-2 text-right tabular-nums ${pnlClass(t.pnl)}`}
                  >
                    {t.pnl != null ? money(t.pnl) : "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-text-muted">
                    {money(t.entry_fee + t.exit_fee)}
                  </td>
                  <td
                    className={`px-3 py-2 text-right font-semibold tabular-nums ${pnlClass(t.net_pnl)}`}
                  >
                    {t.net_pnl != null ? money(t.net_pnl) : "—"}
                  </td>
                  <td className="px-3 py-2 text-right text-text-muted">
                    {fmtDate(t.exit_ts ?? t.entry_ts)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
