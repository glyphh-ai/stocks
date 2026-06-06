"use client";

import { useState } from "react";
import type { GlyphTemplate } from "@/lib/types";
import type { Selection } from "@/lib/glyph";

function isSel(a: Selection, b: Selection): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

const rowBase =
  "group flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-sm transition-colors";

function selCls(active: boolean): string {
  return active
    ? "bg-surface-3 text-text"
    : "text-text-muted hover:bg-surface-2 hover:text-text";
}

function IconBtn({
  label,
  onClick,
  danger,
  children,
}: {
  label: string;
  onClick: () => void;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className={`shrink-0 rounded px-1 text-xs font-medium opacity-0 transition-opacity group-hover:opacity-100 ${
        danger ? "text-text-muted hover:text-bad" : "text-text-muted hover:text-accent"
      }`}
    >
      {children}
    </button>
  );
}

function Caret({ open, onClick }: { open: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={open ? "Collapse" : "Expand"}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className="grid h-4 w-4 shrink-0 place-items-center text-[10px] text-text-muted transition-transform hover:text-text"
      style={{ transform: open ? "rotate(90deg)" : "none" }}
    >
      ▸
    </button>
  );
}

export function BuilderTree({
  template,
  selection,
  onSelect,
  onAddLayer,
  onAddSegment,
  onAddRole,
  onRemove,
}: {
  template: GlyphTemplate;
  selection: Selection;
  onSelect: (s: Selection) => void;
  onAddLayer: () => void;
  onAddSegment: (l: number) => void;
  onAddRole: (l: number, s: number) => void;
  onRemove: (s: Selection) => void;
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const isOpen = (id: string) => !collapsed.has(id);
  const toggle = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="flex flex-col gap-1">
      <button
        onClick={() => onSelect({ kind: "root" })}
        className={`${rowBase} ${selCls(isSel(selection, { kind: "root" }))}`}
      >
        <span className="text-accent">◈</span>
        <span className="truncate font-medium">{template.model}</span>
        <span className="ml-auto text-xs text-text-muted">{template.symbol}</span>
      </button>

      {template.layers.map((layer, l) => {
        const lid = `l${l}`;
        const open = isOpen(lid);
        return (
          <div key={l} className="ml-1">
            <div className={`${rowBase} ${selCls(isSel(selection, { kind: "layer", l }))}`}>
              <Caret open={open} onClick={() => toggle(lid)} />
              <button onClick={() => onSelect({ kind: "layer", l })} className="flex min-w-0 flex-1 items-center gap-1.5 text-left">
                <span className="text-[10px] uppercase text-text-muted">L</span>
                <span className="truncate font-medium text-text">{layer.key}</span>
                <span className="text-xs text-text-muted">{layer.execution === "parallel" ? "∥" : "→"}</span>
              </button>
              <IconBtn label="Add segment" onClick={() => onAddSegment(l)}>+ seg</IconBtn>
              <IconBtn label="Delete layer" danger onClick={() => onRemove({ kind: "layer", l })}>×</IconBtn>
            </div>

            {open &&
              layer.segments.map((seg, s) => {
                const sid = `l${l}s${s}`;
                const sopen = isOpen(sid);
                return (
                  <div key={s} className="ml-3 border-l border-border pl-1">
                    <div className={`${rowBase} ${selCls(isSel(selection, { kind: "segment", l, s }))}`}>
                      <Caret open={sopen} onClick={() => toggle(sid)} />
                      <button onClick={() => onSelect({ kind: "segment", l, s })} className="flex min-w-0 flex-1 items-center gap-1.5 text-left">
                        <span className="text-[10px] uppercase text-text-muted">S</span>
                        <span className="truncate">{seg.key}</span>
                      </button>
                      <IconBtn label="Add role" onClick={() => onAddRole(l, s)}>+ role</IconBtn>
                      <IconBtn label="Delete segment" danger onClick={() => onRemove({ kind: "segment", l, s })}>×</IconBtn>
                    </div>

                    {sopen &&
                      seg.roles.map((role, r) => (
                        <div
                          key={r}
                          className={`${rowBase} ml-3 ${selCls(isSel(selection, { kind: "role", l, s, r }))}`}
                        >
                          <button onClick={() => onSelect({ kind: "role", l, s, r })} className="flex min-w-0 flex-1 items-center gap-1.5 text-left">
                            <span className="text-[10px] uppercase text-text-muted">R</span>
                            <span className="truncate">{role.key}</span>
                            <span className="ml-auto text-xs text-text-muted">{role.type}</span>
                          </button>
                          <IconBtn label="Delete role" danger onClick={() => onRemove({ kind: "role", l, s, r })}>×</IconBtn>
                        </div>
                      ))}
                  </div>
                );
              })}
          </div>
        );
      })}

      <button
        onClick={onAddLayer}
        className="mt-1 rounded-md border border-dashed border-border px-2 py-1.5 text-xs font-medium text-text-muted transition-colors hover:border-accent hover:text-accent"
      >
        + Add layer
      </button>
    </div>
  );
}
