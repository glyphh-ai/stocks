// Shapes mirrored from the FastAPI backend.

export interface SymbolInfo {
  symbol: string;
  interval: string;
  versions: number;
  first_ts: string | null;
  last_ts: string | null;
}

export interface PathInfo {
  level: "cortex" | "layer" | "segment" | "role";
  path: string;
}

export type Metric = "baseline" | "delta" | "value";

export interface Point {
  t: string;
  v: number | null;
}

export interface Series {
  path: string;
  metric: Metric;
  points: Point[];
}

export interface SeriesResponse {
  symbol: string;
  interval: string;
  metric: Metric;
  series: Series[];
}

// ---- Glyph template (config builder) ----

export interface Role {
  key: string;
  type: "scalar" | "symbol";
  range?: [number, number];
  weight: number;
  value?: unknown;
}

export type JobStep =
  | {
      kind: "tool";
      name: string;
      args?: Record<string, unknown>;
      out: string;
      credential?: string;
    }
  | {
      kind: "llm";
      system?: string;
      prompt?: string;
      schema?: Record<string, string>;
      out: string;
    }
  | { kind: "set_role"; role: string; value: string };

export interface Segment {
  key: string;
  weight: number;
  roles: Role[];
  job: JobStep[];
}

export interface Layer {
  key: string;
  weight: number;
  execution: "sequential" | "parallel";
  segments: Segment[];
}

export interface GlyphTemplate {
  model: string;
  symbol: string;
  interval: string;
  dim: number;
  space: string;
  layers: Layer[];
}

export interface TemplateMeta {
  name: string;
  symbol: string;
  updated_at: string | null;
}

export interface TemplateBody {
  name: string;
  symbol: string;
  body: GlyphTemplate;
  updated_at: string | null;
}

export interface TestSegmentResponse {
  roles: Record<string, unknown>;
  error: string | null;
}

export interface BackfillResponse {
  symbol: string;
  interval: string;
  written: number;
  first_ts: string | null;
  last_ts: string | null;
}

export interface QuoteResponse {
  symbol: string;
  price: number;
  prev_close: number | null;
  currency: string;
  ts: string | null;
}

export interface RunResponse {
  version_id: number;
  symbol: string;
  interval: string;
  ts: string;
  roles: Record<string, unknown>;
}

// ---- Tool palette ----

export interface ToolParam {
  name: string;
  type: string;
  required: boolean;
}

export type CredKind = "none" | "bearer" | "basic" | "header";

export interface ToolSpec {
  name: string;
  description: string;
  params: ToolParam[];
  outputs: string[];
  cred_kind: CredKind;
  config: ToolParam[];
}

// ---- Credentials ----

export interface CredentialMeta {
  name: string;
  kind: CredKind;
  updated_at: string | null;
}

// Write-only secret fields the UI collects per credential kind. Secrets are
// sent once and never read back.
export const CRED_FIELDS: Record<Exclude<CredKind, "none">, string[]> = {
  bearer: ["token"],
  basic: ["username", "password"],
  header: ["name", "value"],
};
