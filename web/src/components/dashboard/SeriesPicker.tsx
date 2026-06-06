"use client";

import { useMemo, useState } from "react";
import type { PathInfo } from "@/lib/types";
import { colorForPath } from "@/lib/colors";

type Kind = "cortex" | "layer" | "segment" | "role";

interface Node {
  path: string;
  label: string;
  kind: Kind;
  children: Node[];
}

function buildTree(paths: PathInfo[]): { cortex: Node | null; layers: Node[] } {
  const layerMap = new Map<string, Node>();
  const segMap = new Map<string, Node>();
  let cortex: Node | null = null;

  const ensureLayer = (key: string): Node => {
    let n = layerMap.get(key);
    if (!n) {
      n = { path: `layer:${key}`, label: key, kind: "layer", children: [] };
      layerMap.set(key, n);
    }
    return n;
  };

  const ensureSeg = (layerKey: string, segKey: string): Node => {
    const k = `${layerKey}/${segKey}`;
    let n = segMap.get(k);
    if (!n) {
      n = { path: `segment:${k}`, label: segKey, kind: "segment", children: [] };
      segMap.set(k, n);
      ensureLayer(layerKey).children.push(n);
    }
    return n;
  };

  for (const p of paths) {
    if (p.level === "cortex") {
      cortex = { path: "cortex", label: "cortex", kind: "cortex", children: [] };
    } else if (p.level === "layer") {
      ensureLayer(p.path.slice("layer:".length));
    } else if (p.level === "segment") {
      const [lk, sk] = p.path.slice("segment:".length).split("/");
      ensureSeg(lk, sk);
    } else {
      const [lk, sk, rk] = p.path.slice("role:".length).split("/");
      ensureSeg(lk, sk).children.push({
        path: p.path,
        label: rk,
        kind: "role",
        children: [],
      });
    }
  }

  return { cortex, layers: [...layerMap.values()] };
}

const KIND_LABEL: Record<Kind, string> = {
  cortex: "cortex",
  layer: "layer",
  segment: "segment",
  role: "role",
};

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`transition-transform ${open ? "rotate-90" : ""}`}
    >
      <path d="M9 6l6 6-6 6" />
    </svg>
  );
}

export function SeriesPicker({
  paths,
  selected,
  onToggle,
  keyPrefix = "",
  color,
}: {
  paths: PathInfo[];
  selected: Set<string>;
  onToggle: (path: string) => void;
  /** Prefix applied to selection keys so two trees can share one Set. */
  keyPrefix?: string;
  /** Override the per-node dot color (e.g. green for predictions). */
  color?: (path: string) => string;
}) {
  const { cortex, layers } = useMemo(() => buildTree(paths), [paths]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const dotColor = color ?? colorForPath;

  const toggleCollapse = (path: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });

  const renderNode = (node: Node) => {
    const key = keyPrefix + node.path;
    const on = selected.has(key);
    const hasChildren = node.children.length > 0;
    const isOpen = !collapsed.has(node.path);
    const weight =
      node.kind === "layer"
        ? "font-semibold"
        : node.kind === "segment"
          ? "font-medium"
          : "font-normal";

    return (
      <div key={node.path}>
        <div className="flex items-center gap-0.5">
          {hasChildren ? (
            <button
              onClick={() => toggleCollapse(node.path)}
              aria-label={isOpen ? "Collapse" : "Expand"}
              className="grid h-5 w-5 shrink-0 place-items-center rounded text-text-muted hover:text-text"
            >
              <Chevron open={isOpen} />
            </button>
          ) : (
            <span className="w-5 shrink-0" />
          )}
          <button
            onClick={() => onToggle(key)}
            title={KIND_LABEL[node.kind]}
            className={`group flex min-w-0 flex-1 items-center gap-2 rounded-md px-1.5 py-1 text-left text-sm transition-colors ${
              on ? "bg-surface-3" : "hover:bg-surface-2"
            }`}
          >
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full transition-opacity"
              style={{
                backgroundColor: dotColor(node.path),
                opacity: on ? 1 : 0.25,
              }}
            />
            <span
              className={`truncate ${weight} ${
                on ? "text-text" : "text-text-muted group-hover:text-text"
              }`}
            >
              {node.label}
            </span>
          </button>
        </div>
        {hasChildren && isOpen && (
          <div className="ml-[1.4rem] border-l border-border/60 pl-1">
            {node.children.map(renderNode)}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-0.5">
      {cortex && renderNode(cortex)}
      {layers.map(renderNode)}
    </div>
  );
}
