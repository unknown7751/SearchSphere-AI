const dateFormat = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });

export function formatScore(value, digits = 4) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}

export function formatNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString("en-GB") : "—";
}

export function formatPercent(value, digits = 0) {
  return typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(digits)}%` : "—";
}

export function formatMs(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value < 10 ? `${value.toFixed(2)} ms` : `${Math.round(value)} ms`;
}

export function formatDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : dateFormat.format(d);
}

export function formatBytes(bytes) {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function truncate(text, max = 80) {
  if (typeof text !== "string") return "";
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/**
 * Returns a normalised href only for http(s) URLs; anything else (javascript:, data:, file:, garbage)
 * yields null so callers render plain text instead of a link.
 */
export function safeHttpUrl(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const url = new URL(value.trim());
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

/** Labels and badge tones for the backend's `source_type` values ('seed' | 'user' | 'crawled'). */
export function sourceTypeMeta(type) {
  switch (type) {
    case "crawled":
      return { label: "Crawled", tone: "teal" };
    case "user":
      return { label: "Uploaded", tone: "navy" };
    case "seed":
      return { label: "Seed corpus", tone: "neutral" };
    default:
      return { label: type || "Unknown", tone: "neutral" };
  }
}

export function crawlStatusTone(status) {
  switch (status) {
    case "indexed":
    case "updated":
    case "completed":
      return "green";
    case "running":
    case "queued":
      return "teal";
    case "unchanged":
    case "duplicate_content":
    case "skipped":
    case "cancelled":
      return "neutral";
    case "blocked_by_robots":
    case "blocked_by_security":
      return "amber";
    case "failed":
      return "red";
    default:
      return "neutral";
  }
}

export function humanizeStatus(status) {
  return typeof status === "string" ? status.replaceAll("_", " ") : "—";
}

export function parseIdList(text) {
  const ids = [];
  for (const part of String(text || "").split(/[\s,;]+/)) {
    if (!part) continue;
    const n = Number(part);
    if (!Number.isInteger(n) || n < 1) return { ids: [], error: `"${part}" is not a valid document ID.` };
    if (!ids.includes(n)) ids.push(n);
  }
  return { ids, error: null };
}
