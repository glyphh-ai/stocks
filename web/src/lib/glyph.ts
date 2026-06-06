import type { GlyphTemplate, Layer, Role, Segment } from "./types";

export type Selection =
  | { kind: "root" }
  | { kind: "layer"; l: number }
  | { kind: "segment"; l: number; s: number }
  | { kind: "role"; l: number; s: number; r: number };

export function emptyTemplate(): GlyphTemplate {
  return {
    model: "custom.v1",
    symbol: "AAPL",
    interval: "1m",
    dim: 10000,
    space: "bipolar",
    layers: [],
  };
}

export function newLayer(n: number): Layer {
  return { key: `layer_${n}`, weight: 1.0, execution: "sequential", segments: [] };
}

export function newSegment(n: number): Segment {
  return { key: `segment_${n}`, weight: 1.0, roles: [], job: [] };
}

export function newRole(n: number): Role {
  return { key: `role_${n}`, type: "scalar", range: [0, 100], weight: 1.0 };
}

export function clone<T>(v: T): T {
  return structuredClone(v);
}

export function segmentAt(t: GlyphTemplate, sel: Selection): Segment | null {
  if (sel.kind === "segment") return t.layers[sel.l]?.segments[sel.s] ?? null;
  if (sel.kind === "role") return t.layers[sel.l]?.segments[sel.s] ?? null;
  return null;
}
