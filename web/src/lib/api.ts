import type {
  CredentialMeta,
  CredKind,
  GlyphTemplate,
  Metric,
  PathInfo,
  Segment,
  SeriesResponse,
  SymbolInfo,
  TemplateBody,
  TemplateMeta,
  TestSegmentResponse,
  ToolSpec,
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

  tools: () => http<ToolSpec[]>("/tools"),

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
