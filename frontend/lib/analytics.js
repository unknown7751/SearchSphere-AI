import { sourceTypeMeta } from "./formatters";

/** Pure aggregations over data the backend returned. They count; they never invent values. */

export function countBy(items, keyFn) {
  const counts = new Map();
  for (const item of items) {
    const key = keyFn(item);
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return counts;
}

export function categoryCounts(documents) {
  return [...countBy(documents, (d) => d.category)]
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value || a.name.localeCompare(b.name));
}

export function sourceTypeCounts(documents) {
  return [...countBy(documents, (d) => d.source_type)]
    .map(([type, value]) => ({ name: sourceTypeMeta(type).label, type, value }))
    .sort((a, b) => b.value - a.value);
}

/** Document-length histogram over `word_count` with about `bins` equal-width buckets. */
export function wordCountHistogram(documents, bins = 8) {
  const counts = documents.map((d) => d.word_count).filter((n) => Number.isFinite(n));
  if (counts.length === 0) return [];
  const max = Math.max(...counts);
  const width = Math.max(10, Math.ceil(max / bins / 10) * 10);
  const buckets = [];
  for (let start = 0; start <= max; start += width) buckets.push({ start, end: start + width - 1, value: 0 });
  for (const n of counts) buckets[Math.min(buckets.length - 1, Math.floor(n / width))].value += 1;
  return buckets.map((b) => ({ name: `${b.start}–${b.end}`, value: b.value }));
}

/** Per-job page outcomes for the most recent `limit` jobs, oldest first. */
export function crawlJobSeries(jobs, limit = 10) {
  return [...jobs]
    .sort((a, b) => a.job_id - b.job_id)
    .slice(-limit)
    .map((j) => ({
      name: `#${j.job_id}`,
      crawled: j.pages_crawled,
      blocked: j.pages_blocked,
      failed: j.pages_failed,
    }));
}

export function jobStatusCounts(jobs) {
  return [...countBy(jobs, (j) => j.status)].map(([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value);
}

export function sum(items, key) {
  return items.reduce((total, item) => total + (Number(item[key]) || 0), 0);
}

/** Turn per-mode MAP results into rows keyed by query for a grouped AP chart. */
export function apByQuery(evaluationByMode) {
  const modes = Object.keys(evaluationByMode).filter((m) => evaluationByMode[m]?.ok);
  const queries = new Map();
  for (const mode of modes) {
    for (const q of evaluationByMode[mode].value.per_query) {
      if (!queries.has(q.query)) queries.set(q.query, { name: q.query });
      queries.get(q.query)[mode] = q.average_precision;
    }
  }
  return { modes, rows: [...queries.values()] };
}
