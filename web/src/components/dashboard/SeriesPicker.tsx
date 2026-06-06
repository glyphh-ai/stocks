"use client";

import { useMemo } from "react";
import type { PathInfo } from "@/lib/types";
import { colorForPath, shortLabel } from "@/lib/colors";

const GROUP_ORDER = ["cortex", "layer", "segment", "role"] as const;
const GROUP_LABEL: Record<string, string> = {
  cortex: "Cortex",
  layer: "Layers",
  segment: "Segments",
  role: "Roles",
};

export function SeriesPicker({
  paths,
  selected,
  onToggle,
}: {
  paths: PathInfo[];
  selected: Set<string>;
  onToggle: (path: string) => void;
}) {
  const groups = useMemo(() => {
    const m = new Map<string, PathInfo[]>();
    for (const p of paths) {
      const arr = m.get(p.level) ?? [];
      arr.push(p);
      m.set(p.level, arr);
    }
    return m;
  }, [paths]);

  return (
    <div className="flex flex-col gap-4">
      {GROUP_ORDER.map((level) => {
        const items = groups.get(level);
        if (!items?.length) return null;
        return (
          <div key={level}>
            <div className="mb-1.5 px-1 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
              {GROUP_LABEL[level]}
            </div>
            <div className="flex flex-col gap-0.5">
              {items.map((p) => {
                const on = selected.has(p.path);
                return (
                  <button
                    key={p.path}
                    onClick={() => onToggle(p.path)}
                    className={`group flex items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm transition-colors ${
                      on ? "bg-surface-3" : "hover:bg-surface-2"
                    }`}
                  >
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full transition-opacity"
                      style={{
                        backgroundColor: colorForPath(p.path),
                        opacity: on ? 1 : 0.25,
                      }}
                    />
                    <span className={`truncate ${on ? "text-text" : "text-text-muted group-hover:text-text"}`}>
                      {shortLabel(p.path)}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
