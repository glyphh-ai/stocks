"use client";

import type { AnalysisFactor, TradeAnalysis } from "@/lib/types";

const INFLUENCE: Record<AnalysisFactor["influence"], string> = {
  supportive: "bg-good/15 text-good",
  adverse: "bg-bad/15 text-bad",
  neutral: "bg-surface-2 text-text-muted",
};

export function AnalysisModal({
  data,
  onClose,
}: {
  data: TradeAnalysis;
  onClose: () => void;
}) {
  const { analysis, conditions, llm_available } = data;
  const drift = conditions.layer_drift ?? {};

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
          <h2 className="text-sm font-semibold">Trade analysis</h2>
          <span className="text-[11px] text-text-muted">
            {llm_available ? "Claude" : "heuristic"}
          </span>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 text-sm">
          <p className="leading-relaxed text-text">{analysis.summary}</p>

          {analysis.key_factors.length > 0 && (
            <div>
              <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                Key factors
              </h3>
              <ul className="flex flex-col gap-2">
                {analysis.key_factors.map((f, i) => (
                  <li
                    key={i}
                    className="rounded-lg border border-border bg-surface-2 p-2.5"
                  >
                    <div className="mb-1 flex items-center gap-2">
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${INFLUENCE[f.influence]}`}
                      >
                        {f.influence}
                      </span>
                      <span className="font-mono text-xs text-text">{f.factor}</span>
                    </div>
                    <p className="text-xs leading-relaxed text-text-muted">
                      {f.observation}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {Object.keys(drift).length > 0 && (
            <div>
              <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                Layer drift (entry → exit)
              </h3>
              <div className="flex flex-wrap gap-2">
                {Object.entries(drift).map(([k, v]) => (
                  <span
                    key={k}
                    className="rounded-md border border-border bg-surface-2 px-2 py-1 text-xs"
                  >
                    <span className="text-text-muted">{k.replace("layer:", "")}</span>{" "}
                    <span className="font-medium text-text">{v.toFixed(3)}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          <div>
            <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
              Outlook
            </h3>
            <p className="leading-relaxed text-text-muted">{analysis.outlook}</p>
          </div>
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
