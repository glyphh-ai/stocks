// Stable, vivid series palette that reads well on both themes.
const PALETTE = [
  "#38bdf8", // sky
  "#a78bfa", // violet
  "#34d399", // emerald
  "#fbbf24", // amber
  "#f472b6", // pink
  "#f87171", // red
  "#22d3ee", // cyan
  "#c084fc", // purple
  "#4ade80", // green
  "#fb923c", // orange
  "#818cf8", // indigo
  "#e879f9", // fuchsia
];

export function colorForPath(path: string): string {
  let h = 0;
  for (let i = 0; i < path.length; i++) h = (h * 31 + path.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

export function shortLabel(path: string): string {
  if (path === "cortex") return "cortex";
  const [, body] = path.split(":");
  const parts = body.split("/");
  return parts[parts.length - 1];
}

export function levelOf(path: string): string {
  if (path === "cortex") return "cortex";
  return path.split(":")[0];
}
