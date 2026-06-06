"use client";

import type { PredictionResponse } from "@/lib/types";

function fmt(n: number): string {
  if (Math.abs(n) >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return n.toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function shortRole(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1];
}

export function PredictionModal({
  data,
  onClose,
}: {
  data: PredictionResponse;
  onClose: () => void;
}) {
  const top = data.predictions[0];

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="flex max-h-[82vh] w-full max-w-lg flex-col rounded-xl border border-border bg-surface shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border p-3">
          <h2 className="text-sm font-semibold">Projected next glyph</h2>
          <span className="text-[11px] text-text-muted">
            beam search · {data.basis_versions} versions
          </span>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 text-sm">
          {data.predictions.length === 0 ? (
            <p className="leading-relaxed text-text-muted">
              {data.note ?? "Not enough history to project a next glyph."}
            </p>
          ) : (
            <>
              {data.top_movers && data.top_movers.length > 0 && (
                <div>
                  <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                    Headline moves
                  </h3>
                  <ul className="flex flex-col gap-2">
                    {data.top_movers.map((m) => (
                      <li
                        key={m.role}
                        className="rounded-lg border border-border bg-surface-2 p-2.5"
                      >
                        <div className="mb-1 flex items-center justify-between gap-2">
                          <span className="font-mono text-xs text-text">{shortRole(m.role)}</span>
                          <span
                            className={`text-xs font-semibold ${
                              m.delta >= 0 ? "text-good" : "text-bad"
                            }`}
                          >
                            {m.delta >= 0 ? "+" : ""}
                            {fmt(m.delta)}
                          </span>
                        </div>
                        <p className="text-xs leading-relaxed text-text-muted">
                          {fmt(m.from)} → <span className="text-text">{fmt(m.to)}</span>
                        </p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div>
                <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                  Candidate glyphs
                </h3>
                <div className="flex flex-col gap-2">
                  {data.predictions.map((p) => (
                    <div
                      key={p.rank}
                      className="rounded-lg border border-border bg-surface-2 p-2.5"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-semibold text-text">#{p.rank}</span>
                        <span className="text-text-muted">
                          {(p.confidence * 100).toFixed(0)}% · drift {p.projected_drift.toFixed(4)}
                        </span>
                      </div>
                      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface">
                        <div
                          className="h-full rounded-full bg-accent"
                          style={{ width: `${Math.max(2, p.confidence * 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {top && (
                <p className="text-[11px] leading-relaxed text-text-muted">
                  Projection spans {data.modeled_roles}&nbsp;scalar roles. Drift
                  is the
                  cosine distance of the top candidate&apos;s cortex from the latest
                  recorded glyph — small drift means a steady-state projection.
                </p>
              )}
            </>
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
    </div>
  );
}
