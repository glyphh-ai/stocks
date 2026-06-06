"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Trade, TradeSide } from "@/lib/types";

function nowLocalInput(): string {
  // datetime-local wants "YYYY-MM-DDTHH:mm" in local time.
  const d = new Date();
  const off = d.getTimezoneOffset() * 60_000;
  return new Date(d.getTime() - off).toISOString().slice(0, 16);
}

function toIso(local: string): string {
  return new Date(local).toISOString();
}

type Props =
  | { mode: "open"; symbol: string; interval: string; onClose: () => void; onSaved: () => void }
  | { mode: "close"; trade: Trade; onClose: () => void; onSaved: () => void };

export function TradeModal(props: Props) {
  const symbol = props.mode === "open" ? props.symbol : props.trade.symbol;

  const [side, setSide] = useState<TradeSide>(
    props.mode === "open" ? "long" : props.trade.side,
  );
  const [when, setWhen] = useState(nowLocalInput);
  const [price, setPrice] = useState("");
  const [volume, setVolume] = useState(
    props.mode === "close" ? String(props.trade.volume) : "",
  );
  const [stop, setStop] = useState("");
  const [notes, setNotes] = useState("");

  const [quote, setQuote] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pull the live market price and prefill the price field with it.
  useEffect(() => {
    let alive = true;
    api
      .quote(symbol)
      .then((q) => {
        if (!alive) return;
        setQuote(q.price);
        setPrice((p) => (p === "" ? String(q.price) : p));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [symbol]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      if (props.mode === "open") {
        await api.openTrade({
          symbol,
          interval: props.interval,
          side,
          entry_ts: toIso(when),
          entry_price: Number(price),
          volume: Number(volume),
          stop: stop === "" ? null : Number(stop),
          notes: notes || null,
        });
      } else {
        await api.closeTrade(props.trade.id, {
          exit_ts: toIso(when),
          exit_price: Number(price),
          notes: notes || null,
        });
      }
      props.onSaved();
      props.onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const canSave =
    price !== "" &&
    Number(price) > 0 &&
    (props.mode === "close" || (volume !== "" && Number(volume) > 0));

  const title =
    props.mode === "open"
      ? `New trade · ${symbol}`
      : `Close ${props.trade.side} · ${symbol}`;

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      onClick={props.onClose}
    >
      <div
        className="w-full max-w-sm rounded-xl border border-border bg-surface p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold">{title}</h2>
          <span className="text-xs text-text-muted">
            live{" "}
            {quote == null ? "…" : <span className="font-medium text-text">${quote.toFixed(2)}</span>}
          </span>
        </div>

        <div className="flex flex-col gap-2.5">
          {props.mode === "open" && (
            <div className="flex rounded-lg border border-border bg-surface-2 p-0.5">
              {(["long", "short"] as TradeSide[]).map((s) => (
                <button
                  key={s}
                  onClick={() => setSide(s)}
                  className={`flex-1 rounded-md px-2 py-1 text-xs font-medium capitalize transition-colors ${
                    side === s ? "bg-accent text-accent-fg" : "text-text-muted hover:text-text"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          <Field label={props.mode === "open" ? "Entry time" : "Exit time"}>
            <input
              type="datetime-local"
              value={when}
              onChange={(e) => setWhen(e.target.value)}
              className="w-full rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-sm outline-none focus:border-accent"
            />
          </Field>

          <div className="flex gap-2">
            <Field label={props.mode === "open" ? "Entry price" : "Exit price"}>
              <input
                type="number"
                step="any"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                className="w-full rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-sm outline-none focus:border-accent"
              />
            </Field>
            {props.mode === "open" && (
              <Field label="Volume">
                <input
                  type="number"
                  step="any"
                  value={volume}
                  onChange={(e) => setVolume(e.target.value)}
                  className="w-full rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-sm outline-none focus:border-accent"
                />
              </Field>
            )}
          </div>

          {props.mode === "open" && (
            <Field label="Stop (optional)">
              <input
                type="number"
                step="any"
                value={stop}
                onChange={(e) => setStop(e.target.value)}
                className="w-full rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-sm outline-none focus:border-accent"
              />
            </Field>
          )}

          <Field label="Notes (optional)">
            <input
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-sm outline-none focus:border-accent"
            />
          </Field>

          {error && <p className="text-xs text-bad">{error}</p>}

          <div className="mt-1 flex justify-end gap-2">
            <button
              onClick={props.onClose}
              className="rounded-lg border border-border bg-surface-2 px-3 py-1.5 text-xs font-medium text-text-muted hover:text-text"
            >
              Cancel
            </button>
            <button
              onClick={save}
              disabled={!canSave || saving}
              className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              {saving ? "Saving…" : props.mode === "open" ? "Record trade" : "Record exit"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-1 flex-col gap-1">
      <span className="px-0.5 text-[11px] font-medium uppercase tracking-wider text-text-muted">
        {label}
      </span>
      {children}
    </label>
  );
}
