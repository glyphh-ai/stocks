import type {
  BackfillResponse,
  CredentialMeta,
  CredKind,
  GlyphTemplate,
  Metric,
  PathInfo,
  QuoteResponse,
  RunResponse,
  Segment,
  SeriesResponse,
  SymbolInfo,
  TemplateBody,
  TemplateMeta,
  TestSegmentResponse,
  ToolSpec,
  Trade,
  TradeAnalysis,
  TradeCloseInput,
  TradeOpenInput,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const fetcher = <T>(path: string) => http<T>(path);

export function seriesUrl(
  symbol: string,
  interval: string,
  metric: Metric,
  paths: string[],
): string {
  const qs = new URLSearchParams({ symbol, interval, metric });
  for (const p of paths) qs.append("path", p);
  return `/series?${qs.toString()}`;
}

export const api = {
  symbols: () => http<SymbolInfo[]>("/symbols"),
  paths: (symbol: string, interval: string) =>
    http<PathInfo[]>(
      `/paths?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}`,
    ),
  series: (symbol: string, interval: string, metric: Metric, paths: string[]) =>
    http<SeriesResponse>(seriesUrl(symbol, interval, metric, paths)),

  templates: () => http<TemplateMeta[]>("/templates"),
  template: (name: string) => http<TemplateBody>(`/templates/${encodeURIComponent(name)}`),
  saveTemplate: (name: string, symbol: string, body: GlyphTemplate) =>
    http<TemplateBody>(`/templates/${encodeURIComponent(name)}`, {
      method: "PUT",
      body: JSON.stringify({ symbol, body }),
    }),
  deleteTemplate: (name: string) =>
    http<{ deleted: string }>(`/templates/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),

  testSegment: (symbol: string, interval: string, segment: Segment) =>
    http<TestSegmentResponse>("/jobs/test-segment", {
      method: "POST",
      body: JSON.stringify({ symbol, interval, segment }),
    }),

  backfill: (symbol: string, range = "6mo", interval = "1d") =>
    http<BackfillResponse>("/jobs/backfill", {
      method: "POST",
      body: JSON.stringify({ symbol, range, interval }),
    }),

  quote: (symbol: string) =>
    http<QuoteResponse>(`/jobs/quote?symbol=${encodeURIComponent(symbol)}`),

  run: (symbol: string, interval: string) =>
    http<RunResponse>("/jobs/run", {
      method: "POST",
      body: JSON.stringify({ symbol, interval }),
    }),

  tools: () => http<ToolSpec[]>("/tools"),

  trades: (symbol?: string, interval?: string) => {
    const qs = new URLSearchParams();
    if (symbol) qs.set("symbol", symbol);
    if (interval) qs.set("interval", interval);
    const q = qs.toString();
    return http<Trade[]>(`/trades${q ? `?${q}` : ""}`);
  },
  openTrade: (input: TradeOpenInput) =>
    http<Trade>("/trades", { method: "POST", body: JSON.stringify(input) }),
  closeTrade: (id: number, input: TradeCloseInput) =>
    http<Trade>(`/trades/${id}/close`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
  analyzeTrade: (id: number) =>
    http<TradeAnalysis>(`/trades/${id}/analyze`, { method: "POST" }),
  deleteTrade: (id: number) =>
    http<{ deleted: number }>(`/trades/${id}`, { method: "DELETE" }),

  credentials: () => http<CredentialMeta[]>("/credentials"),
  saveCredential: (name: string, kind: CredKind, fields: Record<string, string>) =>
    http<CredentialMeta>("/credentials", {
      method: "POST",
      body: JSON.stringify({ name, kind, fields }),
    }),
  deleteCredential: (name: string) =>
    http<{ deleted: string }>(`/credentials/${encodeURIComponent(name)}`, {
      method: "DELETE",
    }),
};
