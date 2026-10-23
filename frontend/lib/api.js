/**
 * Central API client for the SearchSphere FastAPI backend.
 *
 * Every request goes through `request()` / `uploadDocument()` so that:
 *  - the base URL comes from NEXT_PUBLIC_API_URL in exactly one place,
 *  - every failure (network, timeout, HTTP error, malformed body) becomes an `ApiError`
 *    with a human-readable message and never exposes a raw stack trace to the UI,
 *  - request timeouts and caller-supplied AbortSignals are handled uniformly.
 *
 * Endpoint paths and payload field names mirror backend/app/api/* and backend/app/schemas/*.
 */

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

const DEFAULT_TIMEOUT_MS = 20000;
const SLOW_TIMEOUT_MS = 60000;

export class ApiError extends Error {
  /**
   * @param {{kind: 'network'|'timeout'|'http'|'malformed'|'aborted', status?: number, code?: string, message: string, details?: any}} info
   */
  constructor({ kind, status = 0, code = null, message, details = null }) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const STATUS_MESSAGES = {
  400: "The request was not valid.",
  404: "The requested item could not be found.",
  409: "The request conflicts with the current state.",
  413: "The uploaded file is too large.",
  415: "That file type is not supported.",
  422: "Some input values were rejected.",
  429: "Too many requests. Please wait a moment and try again.",
  500: "The server hit an unexpected problem. Please try again.",
  502: "The backend is not reachable.",
  503: "The backend is temporarily unavailable.",
  504: "The backend took too long to respond.",
};

/** Build an ApiError from a non-2xx response whose body may or may not follow the backend's error envelope. */
function errorFromResponse(status, body) {
  const envelope = body && typeof body === "object" ? body.error : null;
  let message = envelope && typeof envelope.message === "string" ? envelope.message : null;
  const details = envelope?.details ?? null;
  if (status === 422 && Array.isArray(details) && details.length) {
    const fields = details
      .map((d) => (d && d.field ? `${d.field}: ${d.message}` : d?.message))
      .filter(Boolean)
      .slice(0, 3)
      .join("; ");
    if (fields) message = `${message || STATUS_MESSAGES[422]} (${fields})`;
  }
  // Never surface raw server text for 5xx; the backend already returns a generic message but be defensive.
  if (status >= 500) message = STATUS_MESSAGES[status] || STATUS_MESSAGES[500];
  return new ApiError({
    kind: "http",
    status,
    code: envelope?.code ?? null,
    message: message || STATUS_MESSAGES[status] || `The request failed (HTTP ${status}).`,
    details,
  });
}

function buildUrl(path, query) {
  const url = new URL(`${API_BASE}/api${path}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function request(path, { method = "GET", body, query, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onExternalAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", onExternalAbort, { once: true });
  }

  let response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json", Accept: "application/json" } : { Accept: "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (err) {
    if (timedOut) {
      throw new ApiError({ kind: "timeout", message: "The backend did not respond in time. Check that it is running and try again." });
    }
    if (err?.name === "AbortError") throw new ApiError({ kind: "aborted", message: "The request was cancelled." });
    throw new ApiError({
      kind: "network",
      message: `Cannot reach the SearchSphere backend at ${API_BASE}. Make sure the API server is running.`,
    });
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", onExternalAbort);
  }

  if (response.status === 204) return null;
  let payload = null;
  let parseFailed = false;
  try {
    payload = await response.json();
  } catch {
    parseFailed = true;
  }
  if (!response.ok) throw errorFromResponse(response.status, payload);
  if (parseFailed || payload === null || typeof payload !== "object") {
    throw new ApiError({ kind: "malformed", status: response.status, message: "The backend returned a response the app could not read." });
  }
  return payload;
}

/** Turn any thrown value into `{ title, message, retryable }` for display. */
export function describeError(error) {
  if (error instanceof ApiError) {
    switch (error.kind) {
      case "network":
        return { title: "Backend unavailable", message: error.message, retryable: true };
      case "timeout":
        return { title: "Request timed out", message: error.message, retryable: true };
      case "malformed":
        return { title: "Unexpected response", message: error.message, retryable: true };
      case "aborted":
        return { title: "Cancelled", message: error.message, retryable: true };
      default: {
        const titles = { 400: "Invalid request", 404: "Not found", 409: "Conflict", 413: "File too large", 415: "Unsupported file", 422: "Invalid input" };
        return { title: titles[error.status] || (error.status >= 500 ? "Server error" : "Request failed"), message: error.message, retryable: error.status >= 500 };
      }
    }
  }
  return { title: "Something went wrong", message: "An unexpected error occurred in the page. Please try again.", retryable: true };
}

// ------------------------------------------------------------------ health
export const getHealth = (opts) => request("/health", opts);

// ------------------------------------------------------------------ search
/** TF-IDF / cosine ranked retrieval. `explain: true` adds per-result score breakdowns. */
export const searchDocuments = ({ query, page = 1, pageSize = 10, category, explain = false }, opts) =>
  request("/search", { method: "POST", body: { query, page, page_size: pageSize, category: category || null, explain }, ...opts });

export const expandedSearch = ({ query, page = 1, pageSize = 10, explain = false, feedbackDocs, maxExpansionTerms, expansionWeight }, opts) =>
  request("/search/expanded", {
    method: "POST",
    body: {
      query,
      page,
      page_size: pageSize,
      explain,
      ...(feedbackDocs ? { feedback_docs: feedbackDocs } : {}),
      ...(maxExpansionTerms ? { max_expansion_terms: maxExpansionTerms } : {}),
      ...(expansionWeight ? { expansion_weight: expansionWeight } : {}),
    },
    ...opts,
  });

/** Rocchio-modified search. Pass judged IDs, or `pseudoFeedbackDocs` to treat the top-N baseline results as relevant. */
export const rocchioSearch = (
  { query, page = 1, pageSize = 10, explain = false, relevantDocIds = [], nonRelevantDocIds = [], alpha, beta, gamma, pseudoFeedbackDocs = 0 },
  opts,
) =>
  request("/search/rocchio", {
    method: "POST",
    body: {
      query,
      page,
      page_size: pageSize,
      explain,
      relevant_doc_ids: relevantDocIds,
      non_relevant_doc_ids: nonRelevantDocIds,
      pseudo_feedback_docs: pseudoFeedbackDocs,
      ...(alpha !== undefined ? { alpha } : {}),
      ...(beta !== undefined ? { beta } : {}),
      ...(gamma !== undefined ? { gamma } : {}),
    },
    ...opts,
  });

export const booleanSearch = ({ query, page = 1, pageSize = 20 }, opts) =>
  request("/search/boolean", { method: "POST", body: { query, page, page_size: pageSize }, ...opts });

/** Prefix (`mach*`) and wildcard (`comput*r`) dictionary lookup. */
export const tolerantSearch = ({ pattern, maxExpansions, includeDocuments = true }, opts) =>
  request("/search/tolerant", {
    method: "POST",
    body: { pattern, include_documents: includeDocuments, ...(maxExpansions ? { max_expansions: maxExpansions } : {}) },
    ...opts,
  });

export const getSuggestions = (q, limit = 8, opts) => request("/search/suggestions", { query: { q, limit }, ...opts });

// ------------------------------------------------------------------ documents
export const getDocuments = ({ page = 1, pageSize = 20, category, sourceType } = {}, opts) =>
  request("/documents", { query: { page, page_size: pageSize, category, source_type: sourceType }, ...opts });

export const getDocument = (id, opts) => request(`/documents/${encodeURIComponent(id)}`, opts);

/**
 * Walk the document list (bounded) to summarise the corpus. Used for category lists and analytics.
 * Returns `{ items, total, truncated }`; `truncated` is true when the corpus exceeds `maxPages` pages.
 */
export async function getCorpusOverview({ maxPages = 5, pageSize = 100 } = {}, opts) {
  const items = [];
  let total = 0;
  let totalPages = 1;
  for (let page = 1; page <= Math.min(totalPages, maxPages); page += 1) {
    const res = await getDocuments({ page, pageSize }, opts);
    items.push(...res.items);
    total = res.total;
    totalPages = res.total_pages || 1;
  }
  return { items, total, truncated: items.length < total };
}

/**
 * Upload a TXT/PDF file with real upload progress (fetch cannot report upload progress, XMLHttpRequest can).
 * Resolves with the backend's UploadResponse.
 */
export function uploadDocument(file, { title, category, onProgress, signal } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", file);
    if (title && title.trim()) form.append("title", title.trim());
    if (category && category.trim()) form.append("category", category.trim());

    xhr.open("POST", buildUrl("/documents/upload"));
    xhr.timeout = SLOW_TIMEOUT_MS;
    xhr.setRequestHeader("Accept", "application/json");

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(event.loaded / event.total);
    };
    xhr.upload.onload = () => onProgress && onProgress(1);
    xhr.onerror = () =>
      reject(new ApiError({ kind: "network", message: `Cannot reach the SearchSphere backend at ${API_BASE}. Make sure the API server is running.` }));
    xhr.ontimeout = () => reject(new ApiError({ kind: "timeout", message: "The upload timed out. Try a smaller file." }));
    xhr.onabort = () => reject(new ApiError({ kind: "aborted", message: "The upload was cancelled." }));
    xhr.onload = () => {
      let payload = null;
      try {
        payload = JSON.parse(xhr.responseText);
      } catch {
        payload = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        if (payload && typeof payload === "object") resolve(payload);
        else reject(new ApiError({ kind: "malformed", status: xhr.status, message: "The backend returned a response the app could not read." }));
      } else {
        reject(errorFromResponse(xhr.status, payload));
      }
    };
    if (signal) {
      if (signal.aborted) {
        xhr.abort();
        return;
      }
      signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }
    xhr.send(form);
  });
}

// ------------------------------------------------------------------ crawler
export const validateCrawlUrl = (url, opts) => request("/crawler/validate-url", { method: "POST", body: { url }, timeoutMs: 30000, ...opts });

export const startCrawler = ({ url, maxPages, maxDepth, timeoutSeconds, includeSubdomains, category }, opts) =>
  request("/crawler/start", {
    method: "POST",
    body: {
      url,
      max_pages: maxPages,
      max_depth: maxDepth,
      ...(timeoutSeconds ? { timeout_seconds: timeoutSeconds } : {}),
      ...(includeSubdomains !== undefined ? { include_subdomains: includeSubdomains } : {}),
      ...(category ? { category } : {}),
    },
    timeoutMs: 30000,
    ...opts,
  });

export const getCrawlerStatus = (jobId, opts) => request(`/crawler/${jobId}`, opts);

export const getCrawlerResults = (jobId, { page = 1, pageSize = 50, status } = {}, opts) =>
  request(`/crawler/${jobId}/results`, { query: { page, page_size: pageSize, status }, ...opts });

export const cancelCrawler = (jobId, opts) => request(`/crawler/${jobId}/cancel`, { method: "POST", ...opts });

export const getCrawlerHistory = ({ page = 1, pageSize = 20 } = {}, opts) =>
  request("/crawler/history", { query: { page, page_size: pageSize }, ...opts });

// ------------------------------------------------------------------ workbench
export const preprocessQuery = (text, opts) => request("/workbench/preprocess", { method: "POST", body: { text }, ...opts });

export const getIncidenceMatrix = ({ terms, documentIds }, opts) =>
  request("/workbench/incidence-matrix", { method: "POST", body: { terms, ...(documentIds?.length ? { document_ids: documentIds } : {}) }, ...opts });

/** One term's postings (`term`) or the paginated vocabulary (optionally filtered by `prefix`). */
export const getInvertedIndex = ({ term, prefix, page = 1, pageSize = 50 } = {}, opts) =>
  request("/workbench/inverted-index", { query: { term, prefix, page, page_size: pageSize }, ...opts });

export const getTFIDF = ({ documentIds, query, topN = 10 }, opts) =>
  request("/workbench/tfidf", { method: "POST", body: { document_ids: documentIds, ...(query ? { query } : {}), top_n: topN }, ...opts });

export const getCosine = ({ query, documentIds, topK = 5 }, opts) =>
  request("/workbench/cosine", { method: "POST", body: { query, top_k: topK, ...(documentIds?.length ? { document_ids: documentIds } : {}) }, ...opts });

export const runQueryExpansion = ({ query, topK = 10, feedbackDocs, maxExpansionTerms, expansionWeight }, opts) =>
  request("/workbench/query-expansion", {
    method: "POST",
    body: {
      query,
      top_k: topK,
      ...(feedbackDocs ? { feedback_docs: feedbackDocs } : {}),
      ...(maxExpansionTerms ? { max_expansion_terms: maxExpansionTerms } : {}),
      ...(expansionWeight ? { expansion_weight: expansionWeight } : {}),
    },
    ...opts,
  });

export const runRocchio = (
  { query, relevantDocIds = [], nonRelevantDocIds = [], alpha, beta, gamma, normalize, topK = 10, vectorTerms = 15, pseudoFeedbackDocs = 0 },
  opts,
) =>
  request("/workbench/rocchio", {
    method: "POST",
    body: {
      query,
      relevant_doc_ids: relevantDocIds,
      non_relevant_doc_ids: nonRelevantDocIds,
      top_k: topK,
      vector_terms: vectorTerms,
      pseudo_feedback_docs: pseudoFeedbackDocs,
      ...(alpha !== undefined ? { alpha } : {}),
      ...(beta !== undefined ? { beta } : {}),
      ...(gamma !== undefined ? { gamma } : {}),
      ...(normalize !== undefined ? { normalize } : {}),
    },
    ...opts,
  });

// ------------------------------------------------------------------ evaluation
export const getEvaluationDataset = (opts) => request("/evaluation/dataset", opts);

/** Step-by-step evaluation of one query (every intermediate count and the AP arithmetic). */
export const runEvaluation = ({ query, mode = "tfidf", topK = 10, relevantDocIds, pseudoFeedbackDocs }, opts) =>
  request("/workbench/evaluation", {
    method: "POST",
    body: {
      query,
      mode,
      top_k: topK,
      ...(relevantDocIds?.length ? { relevant_doc_ids: relevantDocIds } : {}),
      ...(pseudoFeedbackDocs !== undefined ? { pseudo_feedback_docs: pseudoFeedbackDocs } : {}),
    },
    ...opts,
  });

/** MAP over the stored evaluation dataset (or supplied judged queries). */
export const runMapEvaluation = ({ mode = "tfidf", topK = 10, queries } = {}, opts) =>
  request("/evaluation/map", { method: "POST", body: { mode, top_k: topK, ...(queries ? { queries } : {}) }, timeoutMs: SLOW_TIMEOUT_MS, ...opts });

// ------------------------------------------------------------------ analytics
/**
 * The backend has no dedicated analytics endpoint, so the dashboard is composed from real endpoints:
 * /health, /documents (corpus overview), /crawler/history and /evaluation/map.
 * Each section is fetched independently; one failing section does not blank the others.
 */
export async function getAnalytics({ evalModes = ["tfidf", "expanded", "rocchio"], topK = 10 } = {}, opts) {
  const settle = (promise) => promise.then((value) => ({ ok: true, value }), (error) => ({ ok: false, error }));
  const [health, corpus, crawl, ...evaluations] = await Promise.all([
    settle(getHealth(opts)),
    settle(getCorpusOverview({}, opts)),
    settle(getCrawlerHistory({ pageSize: 100 }, opts)),
    ...evalModes.map((mode) => settle(runMapEvaluation({ mode, topK }, opts))),
  ]);
  return { health, corpus, crawl, evaluation: Object.fromEntries(evalModes.map((mode, i) => [mode, evaluations[i]])) };
}
