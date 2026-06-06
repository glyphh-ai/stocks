"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { Trade } from "@/lib/types";
import { TradeModal } from "./TradeModal";

function fmtTs(ts: string): string {
  return new Date(ts).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function TradesButton({
  symbol,
  interval,
  onChanged,
}: {
  symbol: string;
  interval: string;
  onChanged?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const { data: trades, mutate } = useSWR<Trade[]>(
    symbol ? `/trades?${symbol}` : null,
    () => api.trades(symbol),
  );

  const openCount = (trades ?? []).filter((t) => t.status === "open").length;

  const refresh = () => {
    mutate();
    onChanged?.();
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        disabled={!symbol}
        title="Record and review trades"
        className="relative rounded-lg border border-border bg-surface-2 px-2.5 py-1 text-xs font-medium text-text-muted transition-colors hover:text-text disabled:opacity-40"
      >
        Trades
        {openCount > 0 && (
          <span className="ml-1.5 rounded-full bg-accent px-1.5 text-[10px] font-semibold text-white">
            {openCount}
          </span>
        )}
      </button>
      {open && (
        <TradesPanel
          symbol={symbol}
          interval={interval}
          trades={trades ?? []}
          onClose={() => setOpen(false)}
          onChanged={refresh}
        />
      )}
    </>
  );
}

function TradesPanel({
  symbol,
  interval,
  trades,
  onClose,
  onChanged,
}: {
  symbol: string;
  interval: string;
  trades: Trade[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const [modal, setModal] = useState<
    { mode: "open" } | { mode: "close"; trade: Trade } | null
  >(null);

  const remove = async (id: number) => {
    await api.deleteTrade(id);
    onChanged();
  };

  return (
    <div
      className="fixed inset-0 z-40 grid place-items-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="flex max-h-[80vh] w-full max-w-lg flex-col rounded-xl border border-border bg-surface shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border p-3">
          <h2 className="text-sm font-semibold">Trades · {symbol}</h2>
          <button
            onClick={() => setModal({ mode: "open" })}
            className="rounded-lg bg-accent px-2.5 py-1 text-xs font-semibold text-white hover:opacity-90"
          >
            + New trade
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {trades.length === 0 ? (
            <p className="px-1 py-6 text-center text-sm text-text-muted">
              No trades yet. Record one with “New trade”.
            </p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {trades.map((t) => (
                <li
                  key={t.id}
                  className="flex items-center gap-3 rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm"
                >
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                      t.side === "long"
                        ? "bg-good/15 text-good"
                        : "bg-bad/15 text-bad"
                    }`}
                  >
                    {t.side}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate">
                      {t.volume} @ ${t.entry_price.toFixed(2)}
                      {t.exit_price != null && ` → $${t.exit_price.toFixed(2)}`}
                    </div>
                    <div className="text-[11px] text-text-muted">
                      {fmtTs(t.entry_ts)}
                      {t.exit_ts && ` → ${fmtTs(t.exit_ts)}`}
                    </div>
                  </div>
                  {t.status === "open" ? (
                    <button
                      onClick={() => setModal({ mode: "close", trade: t })}
                      className="shrink-0 rounded-md border border-border px-2 py-1 text-xs font-medium text-text-muted hover:text-text"
                    >
                      Record exit
                    </button>
                  ) : (
                    <span
                      className={`shrink-0 text-xs font-semibold ${
                        (t.pnl ?? 0) >= 0 ? "text-good" : "text-bad"
                      }`}
                    >
                      {(t.pnl ?? 0) >= 0 ? "+" : ""}
                      {t.pnl?.toFixed(2)}
                    </span>
                  )}
                  <button
                    onClick={() => remove(t.id)}
                    title="Delete trade"
                    className="shrink-0 text-text-muted hover:text-bad"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
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

      {modal?.mode === "open" && (
        <TradeModal
          mode="open"
          symbol={symbol}
          interval={interval}
          onClose={() => setModal(null)}
          onSaved={onChanged}
        />
      )}
      {modal?.mode === "close" && (
        <TradeModal
          mode="close"
          trade={modal.trade}
          onClose={() => setModal(null)}
          onSaved={onChanged}
        />
      )}
    </div>
  );
}
