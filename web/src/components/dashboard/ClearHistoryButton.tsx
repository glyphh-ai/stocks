"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Spinner } from "../Spinner";

function Toggle({
  on,
  onChange,
  label,
}: {
  on: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className="flex items-center gap-2 text-left"
    >
      <span
        className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
          on ? "bg-bad" : "bg-surface-3"
        }`}
      >
        <span
          className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
            on ? "translate-x-4" : "translate-x-0.5"
          }`}
        />
      </span>
      <span className="text-xs font-medium text-text">{label}</span>
    </button>
  );
}

export function ClearHistoryButton({
  symbol,
  interval,
  onCleared,
}: {
  symbol: string;
  interval: string;
  onCleared: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [removeTrades, setRemoveTrades] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setOpen(false);
    setRemoveTrades(false);
    setError(null);
  };

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.clearHistory(symbol, interval, removeTrades);
      onCleared();
      reset();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Clear failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        disabled={!symbol}
        title="Delete all glyph history for this symbol"
        className="rounded-lg border border-bad/40 bg-bad/10 px-2.5 py-1 text-xs font-semibold text-bad transition-colors hover:bg-bad/20 disabled:opacity-40"
      >
        Clear history
      </button>

      {open && (
        <div
          role="alertdialog"
          aria-modal="true"
          className="fixed bottom-4 right-4 z-50 w-80 rounded-xl border border-bad/50 bg-surface p-4 shadow-xl"
        >
          <div className="flex items-start gap-2.5">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="mt-0.5 shrink-0 text-bad"
            >
              <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-text">
                Clear all history for {symbol}?
              </p>
              <p className="mt-1 text-xs text-text-muted">
                This permanently deletes every glyph version and drift record for{" "}
                <span className="font-medium text-text">
                  {symbol} · {interval}
                </span>
                . This cannot be undone.
              </p>
            </div>
          </div>

          <div className="mt-3 rounded-lg border border-border bg-surface-2 p-2.5">
            <Toggle on={removeTrades} onChange={setRemoveTrades} label="Remove trades?" />
            <p className="mt-1 pl-11 text-[11px] text-text-muted">
              {removeTrades
                ? "Recorded trades for this symbol will also be deleted."
                : "Trades are kept by default."}
            </p>
          </div>

          {error && <p className="mt-2 text-xs text-bad">{error}</p>}

          <div className="mt-3 flex justify-end gap-2">
            <button
              onClick={reset}
              disabled={busy}
              className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-xs font-medium text-text-muted hover:text-text disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={confirm}
              disabled={busy}
              className="flex items-center gap-1.5 rounded-lg bg-bad px-3 py-1.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-60"
            >
              {busy ? (
                <>
                  <Spinner /> Clearing
                </>
              ) : removeTrades ? (
                "Clear history + trades"
              ) : (
                "Clear history"
              )}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
