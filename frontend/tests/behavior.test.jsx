import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const router = { push: vi.fn(), replace: vi.fn() };
let currentParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/documents",
  useSearchParams: () => currentParams,
}));

const api = vi.hoisted(() => ({
  getCrawlerStatus: vi.fn(),
  getCrawlerHistory: vi.fn(),
  getCrawlerResults: vi.fn(),
  startCrawler: vi.fn(),
  getDocuments: vi.fn(),
  getCorpusOverview: vi.fn(),
  getEvaluationDataset: vi.fn(),
  uploadDocument: vi.fn(),
}));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal()), ...api }));

import CrawlerPageClient from "@/components/crawler/CrawlerPageClient";
import DocumentsPageClient from "@/components/documents/DocumentsPageClient";
import IngestPanel from "@/components/documents/IngestPanel";
import SearchResults from "@/components/search/SearchResults";
import EvaluationPanel from "@/components/workbench/EvaluationPanel";
import { TabPanel } from "@/components/ui/Tabs";
import { useAsync } from "@/hooks/useAsync";
import { useCrawlJob } from "@/hooks/useCrawler";
import { ApiError } from "@/lib/api";

beforeEach(() => {
  vi.clearAllMocks();
  currentParams = new URLSearchParams();
});
afterEach(() => vi.useRealTimers());

describe("useAsync", () => {
  it("never lets an older response overwrite a newer one", async () => {
    const pending = [];
    const fn = vi.fn((value) => new Promise((resolve) => pending.push(() => resolve(value))));
    const { result } = renderHook(() => useAsync(fn));

    act(() => {
      result.current.run("old");
    });
    act(() => {
      result.current.run("new");
    });
    await act(async () => pending[1]()); // the newer request answers first
    await act(async () => pending[0]()); // the older one answers late
    expect(result.current.data).toBe("new");
    expect(result.current.status).toBe("success");
  });

  it("aborts the in-flight request when it unmounts", () => {
    let seen;
    const fn = vi.fn((_, { signal }) => {
      seen = signal;
      return new Promise(() => {});
    });
    const { result, unmount } = renderHook(() => useAsync(fn));
    act(() => {
      result.current.run("x");
    });
    unmount();
    expect(seen.aborted).toBe(true);
  });
});

describe("useCrawlJob polling", () => {
  const job = (status) => ({ job_id: 7, status });

  it("polls until a terminal status and then stops", async () => {
    vi.useFakeTimers();
    api.getCrawlerStatus.mockResolvedValueOnce(job("queued")).mockResolvedValueOnce(job("running")).mockResolvedValue(job("completed"));
    const { result } = renderHook(() => useCrawlJob(7, { intervalMs: 1000 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.polling).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(result.current.finished).toBe(true);
    expect(result.current.polling).toBe(false);
    expect(api.getCrawlerStatus).toHaveBeenCalledTimes(3);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(api.getCrawlerStatus).toHaveBeenCalledTimes(3);
  });

  it("leaves no timer or request behind after unmount", async () => {
    vi.useFakeTimers();
    let signal;
    api.getCrawlerStatus.mockImplementation(async (_id, opts) => {
      signal = opts.signal;
      return job("running");
    });
    const { unmount } = renderHook(() => useCrawlJob(7, { intervalMs: 1000 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });
    const callsBefore = api.getCrawlerStatus.mock.calls.length;
    expect(callsBefore).toBeGreaterThanOrEqual(3);
    unmount();
    expect(signal.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(api.getCrawlerStatus).toHaveBeenCalledTimes(callsBefore);
  });

  it("stops at once when the job does not exist, and retry() resumes", async () => {
    vi.useFakeTimers();
    api.getCrawlerStatus.mockRejectedValueOnce(new ApiError({ kind: "http", status: 404, code: "crawl_job_not_found", message: "Crawl job 7 does not exist." }));
    const { result } = renderHook(() => useCrawlJob(7, { intervalMs: 1000 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.error).toMatchObject({ status: 404 });
    expect(result.current.polling).toBe(false);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(api.getCrawlerStatus).toHaveBeenCalledTimes(1);

    api.getCrawlerStatus.mockResolvedValue(job("completed"));
    await act(async () => {
      result.current.retry();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.error).toBeNull();
    expect(result.current.finished).toBe(true);
  });

  it("gives up after repeated network failures", async () => {
    vi.useFakeTimers();
    api.getCrawlerStatus.mockRejectedValue(new ApiError({ kind: "network", message: "down" }));
    const { result } = renderHook(() => useCrawlJob(7, { intervalMs: 1000 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20000);
    });
    expect(api.getCrawlerStatus).toHaveBeenCalledTimes(5);
    expect(result.current.error).toMatchObject({ kind: "network" });
  });

  it("does not show one job's error for another job", async () => {
    vi.useFakeTimers();
    api.getCrawlerStatus.mockImplementation(async (id) => {
      if (id === 7) throw new ApiError({ kind: "http", status: 404, message: "gone" });
      return { job_id: id, status: "running" };
    });
    const { result, rerender } = renderHook(({ id }) => useCrawlJob(id, { intervalMs: 1000 }), { initialProps: { id: 7 } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.error).not.toBeNull();
    rerender({ id: 8 });
    expect(result.current.error).toBeNull();
  });
});

describe("SearchResults states", () => {
  const view = (overrides = {}) => ({
    mode: "ranked",
    results: [{ doc_id: 1, title: "Machine Learning", snippet: "s", source_type: "seed", category: "AI/ML", score: 0.5, rank: 1 }],
    total: 1,
    page: 1,
    pageSize: 10,
    tookMs: 1,
    message: null,
    analysis: null,
    extras: {},
    request: { query: "machine", mode: "ranked" },
    ...overrides,
  });

  it("does not show the previous query's results under a new query while loading", () => {
    render(<SearchResults query="python" mode="ranked" state={{ status: "loading", loading: true, data: view(), error: null }} onPageChange={vi.fn()} />);
    expect(screen.getByRole("status", { name: "Loading results" })).toBeInTheDocument();
    expect(screen.queryByText("Machine Learning")).toBeNull();
  });

  it("shows results once they belong to the current query", () => {
    render(<SearchResults query="machine" mode="ranked" state={{ status: "success", loading: false, data: view(), error: null }} onPageChange={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Machine Learning" })).toBeInTheDocument();
  });

  it("explains a page beyond the last one and offers the last page", async () => {
    const onPageChange = vi.fn();
    const beyond = view({ results: [], total: 15, page: 99 });
    render(<SearchResults query="machine" mode="ranked" state={{ status: "success", loading: false, data: beyond, error: null }} onPageChange={onPageChange} />);
    expect(screen.getByText("Page 99 does not exist")).toBeInTheDocument();
    expect(screen.queryByText(/match the filters/)).toBeNull();
    await userEvent.setup().click(screen.getByRole("button", { name: "Go to the last page" }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("keeps the 'no results' message for a genuinely empty search", () => {
    render(<SearchResults query="machine" mode="ranked" state={{ status: "success", loading: false, data: view({ results: [], total: 0 }), error: null }} onPageChange={vi.fn()} />);
    expect(screen.getByText("No documents matched your query.")).toBeInTheDocument();
  });
});

describe("Documents page out of range", () => {
  it("explains a missing page instead of claiming the corpus is empty", async () => {
    currentParams = new URLSearchParams("page=999");
    api.getCorpusOverview.mockResolvedValue({ items: [], total: 0, truncated: false });
    api.getDocuments.mockResolvedValue({ items: [], total: 116, page: 999, page_size: 20, total_pages: 6 });
    render(<DocumentsPageClient />);
    expect(await screen.findByText("Page 999 does not exist")).toBeInTheDocument();
    expect(screen.queryByText("No documents found")).toBeNull();
    await userEvent.setup().click(screen.getByRole("button", { name: "Go to the last page" }));
    expect(router.push).toHaveBeenCalledWith("/documents?page=6");
  });
});

describe("IngestPanel recovery", () => {
  const upload = async (user, name = "a.txt") => {
    await user.upload(document.getElementById("file-input"), new File(["hello"], name, { type: "text/plain" }));
    await user.click(screen.getByRole("button", { name: /Upload and index/ }));
  };

  it("lets the user retry after the server rejects an upload", async () => {
    api.uploadDocument.mockRejectedValueOnce(new ApiError({ kind: "http", status: 400, code: "malformed_pdf", message: "The file is not a readable PDF document." }));
    const user = userEvent.setup();
    render(<IngestPanel />);
    await upload(user);
    expect(await screen.findByText("The file is not a readable PDF document.")).toBeInTheDocument();
    expect(document.getElementById("file-input")).toBeEnabled();
    expect(screen.getByRole("button", { name: /Upload and index/ })).toBeEnabled();

    api.uploadDocument.mockResolvedValueOnce({ document_id: 9, title: "a", file_type: "txt", category: "Uploaded", word_count: 1, token_count: 1, indexed: true, metadata: {} });
    await user.click(screen.getByRole("button", { name: /Upload and index/ }));
    expect(await screen.findByText("Document indexed")).toBeInTheDocument();
    expect(screen.queryByText("The file is not a readable PDF document.")).toBeNull();
  });

  it("links a duplicate upload to the document that already exists", async () => {
    api.uploadDocument.mockRejectedValue(
      new ApiError({ kind: "http", status: 409, code: "duplicate_document", message: "This content is already stored as document 5.", details: { existing_document_id: 5 } }),
    );
    const user = userEvent.setup();
    render(<IngestPanel />);
    await upload(user);
    expect(await screen.findByRole("link", { name: "View existing document #5" })).toHaveAttribute("href", "/documents?id=5");
  });
});

describe("Workbench state", () => {
  it("keeps what was typed in a tab when switching away and back", async () => {
    function Harness() {
      const [tab, setTab] = useState("a");
      return (
        <>
          <button onClick={() => setTab(tab === "a" ? "b" : "a")}>swap</button>
          <TabPanel id="a" active={tab === "a"}>
            <input aria-label="field-a" />
          </TabPanel>
          <TabPanel id="b" active={tab === "b"}>
            <p>panel B</p>
          </TabPanel>
        </>
      );
    }
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.queryByText("panel B")).toBeNull(); // an unvisited tab is not mounted (no requests)
    await user.type(screen.getByLabelText("field-a"), "typed");
    await user.click(screen.getByRole("button", { name: "swap" }));
    expect(screen.getByText("panel B")).toBeVisible();
    expect(screen.getByLabelText("field-a", { selector: "input" })).not.toBeVisible();
    await user.click(screen.getByRole("button", { name: "swap" }));
    expect(screen.getByLabelText("field-a")).toHaveValue("typed");
  });

  it("resets a Boolean evaluation mode when returning to a stored (free-text) query", async () => {
    api.getEvaluationDataset.mockResolvedValue({
      query_count: 1,
      queries: [{ id: 1, query: "machine learning", description: "d", relevant_doc_ids: [30] }],
    });
    const user = userEvent.setup();
    render(<EvaluationPanel />);
    await screen.findByText("Evaluate one query");
    await user.selectOptions(screen.getByLabelText("Query"), "__custom__");
    await user.selectOptions(screen.getByLabelText("Retrieval mode"), "boolean");
    expect(screen.getByLabelText("Retrieval mode")).toHaveValue("boolean");
    await user.selectOptions(screen.getByLabelText("Query"), "machine learning");
    await waitFor(() => expect(screen.getByLabelText("Retrieval mode")).toHaveValue("tfidf"));
  });
});

describe("Crawler page start button", () => {
  const history = (items) => ({ items, total: items.length, page: 1, page_size: 10 });
  const runningJob = { job_id: 9, seed_url: "https://example.com/", status: "running", max_pages: 5, max_depth: 1, timeout_seconds: 10 };

  beforeEach(() => {
    api.getCrawlerResults.mockResolvedValue({ job_id: 9, items: [], total: 0, page: 1, page_size: 25 });
  });

  it("is disabled as soon as a crawl is created, before the first status poll returns", async () => {
    // empty before the start; afterwards the backend's history lists the new queued job
    api.getCrawlerHistory.mockResolvedValueOnce(history([])).mockResolvedValue(history([{ ...runningJob, job_id: 5, status: "queued" }]));
    api.startCrawler.mockResolvedValue({ job_id: 5 });
    api.getCrawlerStatus.mockReturnValue(new Promise(() => {})); // the first poll never answers
    const user = userEvent.setup();
    render(<CrawlerPageClient />);
    await screen.findByText("No crawl jobs yet");
    await user.type(screen.getByLabelText("Seed URL"), "https://example.com/");
    await user.click(screen.getByRole("button", { name: /Start crawl/ }));
    await waitFor(() => expect(api.startCrawler).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole("button", { name: /Start crawl/ })).toBeDisabled());
    expect(screen.getByText(/already queued or running/)).toBeInTheDocument();
  });

  it("re-attaches to an active job after a reload and keeps Start disabled", async () => {
    api.getCrawlerHistory.mockResolvedValue(history([runningJob]));
    api.getCrawlerStatus.mockResolvedValue({ ...runningJob, progress: 0.2, pages_discovered: 5, pages_crawled: 1, pages_failed: 0, pages_blocked: 0, pages_skipped: 0, recent_errors: [], error_count: 0 });
    render(<CrawlerPageClient />);
    expect(await screen.findByText("Crawl job #9")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Start crawl/ })).toBeDisabled();
  });
});
