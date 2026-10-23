import { booleanSearch, expandedSearch, rocchioSearch, searchDocuments, tolerantSearch } from "./api";
import { SEARCH_MODES, SEARCH_PAGE_SIZE } from "./constants";

export function isValidMode(mode) {
  return SEARCH_MODES.some((m) => m.value === mode);
}

/**
 * Call the backend endpoint that implements `mode` and return a uniform view model:
 * { mode, results, total, page, pageSize, tookMs, message, analysis, extras }.
 * No scoring happens here; the model only reshapes what the backend returned.
 */
export async function runSearch({ query, mode, page }, opts) {
  const pageSize = SEARCH_PAGE_SIZE;
  switch (mode) {
    case "boolean":
      return normalizeSearchResponse(mode, await booleanSearch({ query, page, pageSize }, opts), { page, pageSize });
    case "wildcard":
      return normalizeSearchResponse(mode, await tolerantSearch({ pattern: query }, opts), { page, pageSize });
    case "expanded":
      return normalizeSearchResponse(mode, await expandedSearch({ query, page, pageSize, explain: true }, opts), { page, pageSize });
    case "rocchio":
      return normalizeSearchResponse(
        mode,
        await rocchioSearch({ query, page, pageSize, explain: true, pseudoFeedbackDocs: 3 }, opts),
        { page, pageSize },
      );
    default:
      return normalizeSearchResponse("ranked", await searchDocuments({ query, page, pageSize, explain: true }, opts), { page, pageSize });
  }
}

export function normalizeSearchResponse(mode, data, { page, pageSize }) {
  if (mode === "boolean") {
    const offset = (data.page - 1) * data.page_size;
    return {
      mode,
      results: data.results.map((r, i) => ({ ...r, rank: offset + i + 1 })),
      total: data.total_results,
      page: data.page,
      pageSize: data.page_size,
      tookMs: data.took_ms,
      message: data.total_results === 0 ? "No documents matched your query." : null,
      analysis: null,
      extras: {
        boolean: {
          parsedExpression: data.parsed_expression,
          steps: data.steps,
          indexTerms: data.index_terms,
          unknownTerms: data.unknown_terms,
        },
      },
    };
  }
  if (mode === "wildcard") {
    const shown = data.documents;
    const start = (page - 1) * pageSize;
    return {
      mode,
      results: shown.slice(start, start + pageSize).map((r, i) => ({ ...r, rank: start + i + 1 })),
      total: shown.length,
      page,
      pageSize,
      tookMs: data.took_ms,
      message: data.message || (shown.length === 0 ? "No documents matched your query." : null),
      analysis: null,
      extras: {
        wildcard: {
          pattern: data.pattern,
          kind: data.kind,
          strategy: data.strategy,
          matchedTerms: data.matched_terms,
          totalMatches: data.total_matches,
          truncated: data.truncated,
          totalDocuments: data.total_documents,
        },
      },
    };
  }
  return {
    mode,
    results: data.results,
    total: data.total_results,
    page: data.page,
    pageSize: data.page_size,
    tookMs: data.took_ms,
    message: data.total_results === 0 ? data.message || "No documents matched your query." : null,
    analysis: data.query,
    extras: { expansion: data.expansion || null, rocchio: data.rocchio || null, queryVector: data.query_vector || null },
  };
}

/** Client-side filtering of an already retrieved page of results (the backend is not asked again). */
export function filterResults(results, { sourceType, category }) {
  return results.filter((r) => (!sourceType || r.source_type === sourceType) && (!category || r.category === category));
}
