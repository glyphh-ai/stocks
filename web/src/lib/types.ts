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

export interface ClearHistoryResult {
  symbol: string;
  interval: string;
  versions_removed: number;
  trades_removed: number;
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

// ---- Trades ----

export type TradeSide = "long" | "short";
export type TradeStatus = "open" | "closed";

export interface Trade {
  id: number;
  symbol: string;
  interval: string;
  side: TradeSide;
  status: TradeStatus;
  entry_ts: string;
  entry_price: number;
  volume: number;
  stop: number | null;
  entry_version_id: number | null;
  exit_ts: string | null;
  exit_price: number | null;
  exit_version_id: number | null;
  pnl: number | null;
  entry_fee: number;
  exit_fee: number;
  net_pnl: number | null;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
}

// ---- App settings (trade fees) ----

export interface AppSettings {
  commission_per_trade: number;
  per_share: number;
  percent: number;
  updated_at: string | null;
}

export interface SettingsInput {
  commission_per_trade: number;
  per_share: number;
  percent: number;
}

export interface TradeOpenInput {
  symbol: string;
  interval: string;
  side: TradeSide;
  entry_ts: string;
  entry_price: number;
  volume: number;
  stop?: number | null;
  notes?: string | null;
}

export interface TradeCloseInput {
  exit_ts: string;
  exit_price: number;
  notes?: string | null;
}

export interface AnalysisFactor {
  factor: string;
  observation: string;
  influence: "supportive" | "adverse" | "neutral";
}

export interface TradeAnalysis {
  conditions: {
    layer_drift: Record<string, number> | null;
    role_deltas: Record<string, number> | null;
    [k: string]: unknown;
  };
  llm_available: boolean;
  analysis: {
    summary: string;
    key_factors: AnalysisFactor[];
    outlook: string;
  };
}

// ---- Next-glyph prediction (beam search) ----

export interface RoleMove {
  from: number;
  to: number;
  delta: number;
}

export interface GlyphPrediction {
  rank: number;
  score: number;
  confidence: number;
  projected_drift: number;
  roles: Record<string, RoleMove>;
}

export interface TopMover extends RoleMove {
  role: string;
  intensity: number;
}

export interface PredictionResponse {
  symbol: string;
  interval: string;
  basis_versions: number;
  latest_ts: string | null;
  modeled_roles: number;
  predictions: GlyphPrediction[];
  top_movers?: TopMover[];
  note: string | null;
}

// ---- Walk-forward backtest ----

export interface BacktestPoint {
  ts: string;
  prev: number;
  predicted: number;
  actual: number;
  confidence: number;
}

export interface BacktestMetrics {
  n: number;
  directional_accuracy: number | null;
  directional_n: number;
  mae: number;
  mape: number | null;
  rmse: number;
  naive_mae: number;
  skill_vs_naive: number | null;
  mean_confidence: number;
}

export interface BacktestResult {
  symbol: string;
  interval: string;
  basis_versions: number;
  warmup: number;
  price_path?: string;
  points: BacktestPoint[];
  metrics: BacktestMetrics | null;
  note: string | null;
}

export interface BacktestImprovement {
  idea: string;
  rationale: string;
  expected_impact: "high" | "medium" | "low";
}

export interface BacktestAnalysisBody {
  assessment: string;
  beam_strengths: string[];
  beam_weaknesses: string[];
  improvements: BacktestImprovement[];
  verdict: "signal" | "inconclusive" | "no_signal";
}

export interface BacktestAnalysis {
  backtest: {
    symbol: string;
    interval: string;
    metrics: BacktestMetrics | null;
    note?: string | null;
  };
  llm_available: boolean;
  analysis: BacktestAnalysisBody;
}

// ---- Ensemble next-glyph prediction (persisted, green tree) ----

export interface PredictionSeries {
  path: string;
  points: Point[];
}

export interface PredictionSeriesResponse {
  symbol: string;
  interval: string;
  series: PredictionSeries[];
}

export interface SignalComponents {
  autoregressive: number | null;
  beam: number | null;
  trades: number;
  llm: number;
  from: number;
  final: number;
  delta: number;
}

export interface NextPredictionBody {
  target_ts: string;
  basis_versions: number;
  confidence: number;
  components: Record<string, SignalComponents>;
  glyph: GlyphTemplate;
}

export interface NextPredictionResponse {
  symbol: string;
  interval: string;
  prediction: NextPredictionBody | null;
}

export interface RefreshPredictionsResponse {
  symbol: string;
  interval: string;
  history_rows: number;
  ahead: unknown;
  llm_available?: boolean;
  note: string | null;
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
