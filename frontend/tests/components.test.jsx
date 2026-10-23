import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

const api = vi.hoisted(() => ({
  validateCrawlUrl: vi.fn(),
  startCrawler: vi.fn(),
  uploadDocument: vi.fn(),
  searchDocuments: vi.fn(),
  preprocessQuery: vi.fn(),
}));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal()), ...api }));

import SearchBox from "@/components/search/SearchBox";
import ResultCard from "@/components/search/ResultCard";
import CrawlForm from "@/components/crawler/CrawlForm";
import IngestPanel, { validateFile } from "@/components/documents/IngestPanel";
import PreprocessingPanel from "@/components/workbench/PreprocessingPanel";
import SafeLink from "@/components/ui/SafeLink";
import Tabs from "@/components/ui/Tabs";
import { ApiError } from "@/lib/api";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("SearchBox", () => {
  it("navigates to a shareable URL on Enter", async () => {
    const user = userEvent.setup();
    render(<SearchBox />);
    await user.type(screen.getByRole("searchbox", { name: "Search query" }), "machine learning{Enter}");
    expect(push).toHaveBeenCalledWith("/search?q=machine+learning");
  });

  it("includes the selected mode and ignores empty queries", async () => {
    const user = userEvent.setup();
    render(<SearchBox />);
    expect(screen.getByRole("button", { name: "Search" })).toBeDisabled();
    await user.click(screen.getByLabelText("Boolean"));
    await user.type(screen.getByRole("searchbox"), "a AND b{Enter}");
    expect(push).toHaveBeenCalledWith("/search?q=a+AND+b&mode=boolean");
  });

  it("offers only modes the backend implements", () => {
    render(<SearchBox />);
    const labels = screen.getAllByRole("radio").map((r) => r.parentElement.textContent);
    expect(labels).toEqual(["Ranked search", "Ranked + expansion", "Pseudo-feedback", "Boolean", "Prefix / wildcard"]);
  });
});

describe("ResultCard", () => {
  const result = {
    rank: 1,
    doc_id: 9,
    title: "<img src=x onerror=alert(1)> Title",
    category: "Web pages",
    snippet: "<script>alert(1)</script> snippet",
    score: 0.4,
    source_type: "crawled",
    source_url: "javascript:alert(1)",
    explanation: {
      dot_product: 2,
      query_norm: 1,
      document_norm: 5,
      matching_terms: [{ term: "learn", word: "learning", tf: 2, df: 8, idf: 3.5, tfidf: 7, query_weight: 3.5, contribution: 24 }],
    },
  };

  it("renders untrusted text as text and never links unsafe URLs", () => {
    const { container } = render(<ResultCard result={result} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText(/<script>alert\(1\)<\/script> snippet/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /javascript/i })).toBeNull();
    expect(container.querySelector('a[href^="javascript"]')).toBeNull();
    expect(screen.getByText("Crawled", { selector: "span" })).toBeInTheDocument();
  });

  it("expands the explanation with TF, DF, IDF and the cosine arithmetic", async () => {
    const user = userEvent.setup();
    render(<ResultCard result={result} />);
    expect(screen.queryByText(/cosine =/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "Why this result?" }));
    expect(screen.getByRole("columnheader", { name: "TF" })).toBeInTheDocument();
    expect(screen.getByText(/cosine = dot\(q,d\)/)).toBeInTheDocument();
  });
});

describe("SafeLink", () => {
  it("links https and blocks other schemes", () => {
    const { rerender } = render(<SafeLink href="https://example.com/x" />);
    expect(screen.getByRole("link")).toHaveAttribute("rel", expect.stringContaining("noopener"));
    rerender(<SafeLink href="data:text/html,x" />);
    expect(screen.queryByRole("link")).toBeNull();
  });
});

describe("Tabs", () => {
  it("moves between tabs with the arrow keys", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Tabs tabs={[{ id: "a", label: "A" }, { id: "b", label: "B" }]} value="a" onChange={onChange} label="t" />);
    screen.getByRole("tab", { name: "A" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenCalledWith("b");
  });
});

describe("CrawlForm", () => {
  it("shows a blocked validation result with its reason", async () => {
    api.validateCrawlUrl.mockResolvedValue({ url: "http://127.0.0.1/", allowed: false, status: "blocked_by_security", reason: "loopback_address", message: "The address is blocked: loopback addresses are not allowed." });
    const user = userEvent.setup();
    render(<CrawlForm onStarted={vi.fn()} />);
    await user.type(screen.getByLabelText("Seed URL"), "http://127.0.0.1/");
    await user.click(screen.getByRole("button", { name: "Validate URL" }));
    expect(await screen.findByText("Blocked")).toBeInTheDocument();
    expect(screen.getByText("loopback_address")).toBeInTheDocument();
  });

  it("starts a crawl with the entered bounds", async () => {
    api.startCrawler.mockResolvedValue({ job_id: 3 });
    const onStarted = vi.fn();
    const user = userEvent.setup();
    render(<CrawlForm onStarted={onStarted} />);
    await user.type(screen.getByLabelText("Seed URL"), "https://example.com/");
    await user.clear(screen.getByLabelText("Max pages"));
    await user.type(screen.getByLabelText("Max pages"), "5");
    await user.click(screen.getByRole("button", { name: /Start crawl/ }));
    await waitFor(() => expect(onStarted).toHaveBeenCalledWith({ job_id: 3 }));
    expect(api.startCrawler).toHaveBeenCalledWith({ url: "https://example.com/", maxPages: 5, maxDepth: 2 });
  });

  it("rejects out-of-range limits before calling the backend", async () => {
    const user = userEvent.setup();
    render(<CrawlForm onStarted={vi.fn()} />);
    await user.type(screen.getByLabelText("Seed URL"), "https://example.com/");
    await user.clear(screen.getByLabelText("Max pages"));
    await user.type(screen.getByLabelText("Max pages"), "500");
    expect(screen.getByText(/whole number from 1 to 100/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Start crawl/ })).toBeDisabled();
  });

  it("surfaces a conflict from the backend", async () => {
    api.startCrawler.mockRejectedValue(new ApiError({ kind: "http", status: 409, code: "crawl_in_progress", message: "Another crawl is queued or running." }));
    const user = userEvent.setup();
    render(<CrawlForm onStarted={vi.fn()} />);
    await user.type(screen.getByLabelText("Seed URL"), "https://example.com/");
    await user.click(screen.getByRole("button", { name: /Start crawl/ }));
    expect(await screen.findByText("Another crawl is queued or running.")).toBeInTheDocument();
  });
});

describe("IngestPanel", () => {
  it("validates file type and size", () => {
    expect(validateFile(new File(["x"], "a.docx"))).toMatch(/Only .txt and .pdf/);
    expect(validateFile(new File([], "a.txt"))).toMatch(/empty/);
    expect(validateFile(new File(["x"], "a.TXT"))).toBeNull();
    const big = new File(["x"], "b.pdf");
    Object.defineProperty(big, "size", { value: 6 * 1024 * 1024 });
    expect(validateFile(big)).toMatch(/limit/);
  });

  it("uploads a file and offers to search it", async () => {
    api.uploadDocument.mockImplementation(async (_file, { onProgress }) => {
      onProgress(1);
      return { document_id: 42, title: "Notes", file_type: "txt", category: "Uploaded", word_count: 10, token_count: 8, indexed: true, metadata: {} };
    });
    const user = userEvent.setup();
    render(<IngestPanel />);
    await user.upload(document.getElementById("file-input"), new File(["hello world"], "notes.txt", { type: "text/plain" }));
    await user.click(screen.getByRole("button", { name: /Upload and index/ }));
    expect(await screen.findByText("Document indexed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Search this document/ })).toHaveAttribute("href", "/search?q=Notes");
    expect(screen.getByRole("link", { name: "View document" })).toHaveAttribute("href", "/documents?id=42");
  });

  it("shows the backend's rejection", async () => {
    api.uploadDocument.mockRejectedValue(new ApiError({ kind: "http", status: 409, code: "duplicate_document", message: "This content is already stored as document 5." }));
    const user = userEvent.setup();
    render(<IngestPanel />);
    await user.upload(document.getElementById("file-input"), new File(["hello"], "a.txt", { type: "text/plain" }));
    await user.click(screen.getByRole("button", { name: /Upload and index/ }));
    expect(await screen.findByText("This content is already stored as document 5.")).toBeInTheDocument();
  });
});

describe("Workbench preprocessing", () => {
  it("renders every stage returned by the backend", async () => {
    api.preprocessQuery.mockResolvedValue({
      original: "The Running Dogs",
      normalized: "the running dogs",
      tokens: ["the", "running", "dogs"],
      stop_words_removed: ["the"],
      tokens_without_stopwords: ["running", "dogs"],
      stemmed_tokens: ["run", "dog"],
      lemmatized_tokens: ["run", "dog"],
      index_terms: ["run", "dog"],
      index_form: "stem",
    });
    const user = userEvent.setup();
    render(<PreprocessingPanel />);
    await user.click(screen.getByRole("button", { name: "Run preprocessing" }));
    expect(await screen.findByText("Pipeline stages")).toBeInTheDocument();
    expect(screen.getByText("2 · Tokenisation")).toBeInTheDocument();
    expect(screen.getByText("4 · Stemming (Porter)")).toBeInTheDocument();
    expect(screen.getByText("the running dogs")).toBeInTheDocument();
  });
});
