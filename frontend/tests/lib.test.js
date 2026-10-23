import { describe, expect, it, vi, afterEach } from "vitest";
import { apByQuery, categoryCounts, crawlJobSeries, wordCountHistogram } from "@/lib/analytics";
import { ApiError, describeError, getDocuments, runMapEvaluation, searchDocuments, uploadDocument } from "@/lib/api";
import { formatBytes, formatDate, formatScore, parseIdList, safeHttpUrl, sourceTypeMeta } from "@/lib/formatters";
import { filterResults, normalizeSearchResponse } from "@/lib/searchModel";
import { searchHref } from "@/lib/searchUrl";

afterEach(() => vi.unstubAllGlobals());

function mockFetch(status, body, { json = true } = {}) {
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: json ? async () => body : async () => Promise.reject(new SyntaxError("bad json")),
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("formatters", () => {
  it("only allows http(s) URLs as links", () => {
    expect(safeHttpUrl("https://example.com/a?b=1")).toBe("https://example.com/a?b=1");
    expect(safeHttpUrl("http://example.com")).toBe("http://example.com/");
    for (const bad of ["javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,<b>x</b>", "file:///etc/passwd", "//evil.com", "not a url", "", null, undefined, 42]) {
      expect(safeHttpUrl(bad)).toBeNull();
    }
  });

  it("formats numbers, bytes and dates defensively", () => {
    expect(formatScore(0.40697, 4)).toBe("0.4070");
    expect(formatScore(null)).toBe("—");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(-1)).toBe("—");
    expect(formatDate("not a date")).toBe("—");
    expect(formatDate(null)).toBe("—");
  });

  it("labels the backend's source types", () => {
    expect(sourceTypeMeta("crawled").label).toBe("Crawled");
    expect(sourceTypeMeta("user").label).toBe("Uploaded");
    expect(sourceTypeMeta("seed").label).toBe("Seed corpus");
    expect(sourceTypeMeta("weird").label).toBe("weird");
  });

  it("parses document ID lists", () => {
    expect(parseIdList("30, 31 31;32")).toEqual({ ids: [30, 31, 32], error: null });
    expect(parseIdList("30, abc").error).toMatch(/abc/);
    expect(parseIdList("0").error).toBeTruthy();
    expect(parseIdList("").ids).toEqual([]);
  });

  it("builds shareable search URLs", () => {
    expect(searchHref("machine learning", "ranked")).toBe("/search?q=machine+learning");
    expect(searchHref(" mach* ", "wildcard")).toBe("/search?q=mach*&mode=wildcard");
  });
});

describe("api client", () => {
  it("posts search requests with the backend's field names", async () => {
    const fetchMock = mockFetch(200, { results: [] });
    await searchDocuments({ query: "q", pageSize: 5, explain: true });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/search");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ query: "q", page: 1, page_size: 5, category: null, explain: true });
  });

  it("sends query parameters and skips empty ones", async () => {
    const fetchMock = mockFetch(200, { items: [] });
    await getDocuments({ page: 2, pageSize: 20, sourceType: "crawled" });
    const url = new URL(fetchMock.mock.calls[0][0]);
    expect(url.pathname).toBe("/api/documents");
    expect(url.searchParams.get("source_type")).toBe("crawled");
    expect(url.searchParams.has("category")).toBe(false);
  });

  it("maps the backend error envelope to a readable ApiError", async () => {
    mockFetch(400, { error: { code: "invalid_boolean_query", message: "Missing operator before 'learning'.", details: { position: 8 } } });
    await expect(searchDocuments({ query: "x" })).rejects.toMatchObject({ kind: "http", status: 400, code: "invalid_boolean_query", message: "Missing operator before 'learning'." });
  });

  it("summarises 422 validation details", async () => {
    mockFetch(422, { error: { code: "validation_error", message: "Request validation failed.", details: [{ field: "query", message: "Field required" }] } });
    await expect(searchDocuments({ query: "x" })).rejects.toThrow(/query: Field required/);
  });

  it("never exposes server text for 5xx errors", async () => {
    mockFetch(500, { error: { code: "internal_error", message: "Traceback (most recent call last): ..." } });
    const error = await searchDocuments({ query: "x" }).catch((e) => e);
    expect(error.message).not.toMatch(/Traceback/);
    expect(describeError(error)).toMatchObject({ title: "Server error", retryable: true });
  });

  it("reports an unreachable backend", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await searchDocuments({ query: "x" }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.kind).toBe("network");
    expect(describeError(error).title).toBe("Backend unavailable");
  });

  it("treats a non-JSON success body as malformed", async () => {
    mockFetch(200, null, { json: false });
    await expect(searchDocuments({ query: "x" })).rejects.toMatchObject({ kind: "malformed" });
  });

  it("times out slow requests", async () => {
    vi.stubGlobal("fetch", vi.fn((_, init) => new Promise((_, reject) => init.signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" }))))));
    const error = await runMapEvaluation({}, { timeoutMs: 20 }).catch((e) => e);
    expect(error.kind).toBe("timeout");
  });

  it("uploads files as multipart with progress", async () => {
    const instances = [];
    class FakeXhr {
      constructor() {
        this.upload = {};
        this.headers = {};
        instances.push(this);
      }
      open(method, url) {
        this.method = method;
        this.url = url;
      }
      setRequestHeader() {}
      send(form) {
        this.form = form;
        this.upload.onprogress({ lengthComputable: true, loaded: 5, total: 10 });
        this.upload.onload();
        this.status = 201;
        this.responseText = JSON.stringify({ document_id: 7, title: "t" });
        this.onload();
      }
    }
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    const progress = [];
    const file = new File(["hello"], "a.txt", { type: "text/plain" });
    const result = await uploadDocument(file, { title: "T", category: "Uploaded", onProgress: (p) => progress.push(p) });
    expect(result.document_id).toBe(7);
    expect(instances[0].url).toBe("http://localhost:8000/api/documents/upload");
    expect(instances[0].form.get("file").name).toBe("a.txt");
    expect(instances[0].form.get("title")).toBe("T");
    expect(progress).toEqual([0.5, 1]);
  });
});

describe("search model", () => {
  const base = { took_ms: 1.5, page: 1, page_size: 10 };

  it("normalises ranked results without touching scores", () => {
    const data = { ...base, query: { original: "q" }, results: [{ doc_id: 1, score: 0.5, source_type: "seed" }], total_results: 1, message: null };
    const view = normalizeSearchResponse("ranked", data, { page: 1, pageSize: 10 });
    expect(view.results[0].score).toBe(0.5);
    expect(view.total).toBe(1);
    expect(view.tookMs).toBe(1.5);
  });

  it("numbers Boolean results and reports an empty set", () => {
    const data = { ...base, page: 2, page_size: 2, results: [{ doc_id: 5 }, { doc_id: 6 }], total_results: 4, parsed_expression: "(a AND b)", steps: [], index_terms: {}, unknown_terms: [] };
    const view = normalizeSearchResponse("boolean", data, { page: 2, pageSize: 2 });
    expect(view.results.map((r) => r.rank)).toEqual([3, 4]);
    expect(view.extras.boolean.parsedExpression).toBe("(a AND b)");
    const empty = normalizeSearchResponse("boolean", { ...data, results: [], total_results: 0 }, { page: 1, pageSize: 10 });
    expect(empty.message).toBe("No documents matched your query.");
  });

  it("paginates wildcard documents client-side", () => {
    const documents = Array.from({ length: 25 }, (_, i) => ({ doc_id: i + 1 }));
    const data = { took_ms: 1, pattern: "a*", kind: "prefix", strategy: "s", matched_terms: [], total_matches: 1, truncated: false, total_documents: 25, documents, message: null };
    const view = normalizeSearchResponse("wildcard", data, { page: 3, pageSize: 10 });
    expect(view.results.map((r) => r.doc_id)).toEqual([21, 22, 23, 24, 25]);
    expect(view.total).toBe(25);
  });

  it("filters retrieved results client-side", () => {
    const results = [
      { doc_id: 1, source_type: "seed", category: "AI/ML" },
      { doc_id: 2, source_type: "crawled", category: "Crawled" },
    ];
    expect(filterResults(results, { sourceType: "crawled" }).map((r) => r.doc_id)).toEqual([2]);
    expect(filterResults(results, { category: "AI/ML" }).map((r) => r.doc_id)).toEqual([1]);
    expect(filterResults(results, {})).toHaveLength(2);
  });
});

describe("analytics aggregation", () => {
  it("counts categories and builds a histogram", () => {
    const docs = [
      { category: "A", word_count: 5 },
      { category: "B", word_count: 45 },
      { category: "A", word_count: 47 },
    ];
    expect(categoryCounts(docs)).toEqual([{ name: "A", value: 2 }, { name: "B", value: 1 }]);
    const hist = wordCountHistogram(docs, 5);
    expect(hist.reduce((n, b) => n + b.value, 0)).toBe(3);
    expect(wordCountHistogram([])).toEqual([]);
  });

  it("orders crawl jobs oldest first and limits them", () => {
    const jobs = [3, 1, 2].map((id) => ({ job_id: id, pages_crawled: id, pages_blocked: 0, pages_failed: 0 }));
    expect(crawlJobSeries(jobs, 2).map((j) => j.name)).toEqual(["#2", "#3"]);
  });

  it("pivots per-mode evaluations by query", () => {
    const ev = {
      tfidf: { ok: true, value: { per_query: [{ query: "q1", average_precision: 0.5 }] } },
      rocchio: { ok: true, value: { per_query: [{ query: "q1", average_precision: 0.7 }] } },
      expanded: { ok: false, error: new Error("x") },
    };
    const { modes, rows } = apByQuery(ev);
    expect(modes).toEqual(["tfidf", "rocchio"]);
    expect(rows).toEqual([{ name: "q1", tfidf: 0.5, rocchio: 0.7 }]);
  });
});
