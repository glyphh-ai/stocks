"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { AppSettings } from "@/lib/types";
import { Spinner } from "../Spinner";

const FIELDS: {
  key: keyof Omit<AppSettings, "updated_at">;
  label: string;
  hint: string;
  prefix?: string;
  suffix?: string;
}[] = [
  {
    key: "commission_per_trade",
    label: "Commission per trade",
    hint: "Flat fee charged on each leg (entry and exit).",
    prefix: "$",
  },
  {
    key: "per_share",
    label: "Per-share fee",
    hint: "Charged per share/contract on each leg.",
    prefix: "$",
  },
  {
    key: "percent",
    label: "Percent of notional",
    hint: "Percent of price × volume on each leg.",
    suffix: "%",
  },
];

export function SettingsTab() {
  const { data, mutate } = useSWR<AppSettings>("/settings", () => api.settings());
  const [form, setForm] = useState({
    commission_per_trade: "0",
    per_share: "0",
    percent: "0",
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setForm({
        commission_per_trade: String(data.commission_per_trade),
        per_share: String(data.per_share),
        percent: String(data.percent),
      });
    }
  }, [data]);

  const save = async () => {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const input = {
        commission_per_trade: parseFloat(form.commission_per_trade) || 0,
        per_share: parseFloat(form.per_share) || 0,
        percent: parseFloat(form.percent) || 0,
      };
      await api.saveSettings(input);
      await mutate();
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="text-lg font-semibold tracking-tight">Settings</h1>
      <p className="mt-1 text-sm text-text-muted">
        Trading-platform costs. Fees are applied to each leg of a trade, so a
        round trip pays the entry and exit fee. Net P&amp;L on the Trades tab
        subtracts these from the gross.
      </p>

      <div className="mt-6 rounded-xl border border-border bg-surface p-5">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
          Trade fees
        </h2>
        <div className="mt-3 flex flex-col gap-4">
          {FIELDS.map((f) => (
            <label key={f.key} className="flex flex-col gap-1">
              <span className="text-sm font-medium text-text">{f.label}</span>
              <span className="text-xs text-text-muted">{f.hint}</span>
              <div className="mt-1 flex items-center gap-2">
                {f.prefix && (
                  <span className="text-sm text-text-muted">{f.prefix}</span>
                )}
                <input
                  type="number"
                  min={0}
                  step="any"
                  value={form[f.key]}
                  onChange={(e) =>
                    setForm((p) => ({ ...p, [f.key]: e.target.value }))
                  }
                  className="w-40 rounded-lg border border-border bg-surface-2 px-2.5 py-1.5 text-sm outline-none focus:border-accent"
                />
                {f.suffix && (
                  <span className="text-sm text-text-muted">{f.suffix}</span>
                )}
              </div>
            </label>
          ))}
        </div>

        <div className="mt-5 flex items-center gap-3 border-t border-border pt-4">
          <button
            onClick={save}
            disabled={saving}
            className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {saving ? (
              <>
                <Spinner /> Saving
              </>
            ) : (
              "Save fees"
            )}
          </button>
          {saved && <span className="text-xs text-good">Saved</span>}
          {error && <span className="text-xs text-bad">{error}</span>}
          {data?.updated_at && !saved && (
            <span className="text-xs text-text-muted">
              Last updated {new Date(data.updated_at).toLocaleString()}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
