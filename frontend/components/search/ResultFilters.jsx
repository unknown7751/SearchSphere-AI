import { sourceTypeMeta } from "@/lib/formatters";

/**
 * Filters over the page of results that was already retrieved. The backend search endpoints have no
 * source-type filter, so this is deliberately client-side and labelled as such.
 */
export default function ResultFilters({ results, sourceType, category, onChange }) {
  const sourceTypes = [...new Set(results.map((r) => r.source_type))].sort();
  const categories = [...new Set(results.map((r) => r.category).filter(Boolean))].sort();
  if (sourceTypes.length < 2 && categories.length < 2) return null;

  return (
    <div className="flex flex-wrap items-end gap-x-6 gap-y-2 rounded border border-mute-line bg-white px-3 py-2 text-sm">
      {sourceTypes.length > 1 && (
        <div role="group" aria-label="Filter by source type" className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-mute">Source</span>
          {[null, ...sourceTypes].map((type) => {
            const active = (sourceType || null) === type;
            return (
              <button
                key={type || "all"}
                type="button"
                aria-pressed={active}
                onClick={() => onChange({ sourceType: type, category })}
                className={`rounded border px-2 py-0.5 text-xs ${
                  active ? "border-teal-600 bg-teal-50 text-teal-800" : "border-mute-line text-ink-soft hover:bg-paper-dark"
                }`}
              >
                {type ? sourceTypeMeta(type).label : "All"}
              </button>
            );
          })}
        </div>
      )}
      {categories.length > 1 && (
        <label className="flex items-center gap-2">
          <span className="text-mute">Category</span>
          <select
            value={category || ""}
            onChange={(e) => onChange({ sourceType, category: e.target.value || null })}
            className="h-8 rounded border border-mute-light bg-white px-2 text-sm"
          >
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
      )}
      <span className="ml-auto text-xs text-mute">Filters apply to the results on this page only.</span>
    </div>
  );
}
