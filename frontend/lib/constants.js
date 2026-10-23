export const APP_NAME = "SearchSphere AI";
export const APP_TAGLINE =
  "An interactive Information Retrieval laboratory for exploring document search, ranking, indexing, relevance feedback, and evaluation.";

export const NAV_ITEMS = [
  { href: "/", label: "Search", match: ["/", "/search"] },
  { href: "/documents", label: "Explore", match: ["/documents"] },
  { href: "/workbench", label: "Workbench", match: ["/workbench"] },
  { href: "/analytics", label: "Analytics", match: ["/analytics"] },
  { href: "/crawler", label: "Crawler", match: ["/crawler"] },
  { href: "/ingest", label: "Library", match: ["/ingest"] },
  { href: "/docs", label: "Documentation", match: ["/docs"] },
];

// Search modes the backend actually implements (see backend/app/api/search.py).
export const SEARCH_MODES = [
  { value: "ranked", label: "Ranked search", hint: "TF-IDF weights, cosine similarity ranking", placeholder: "machine learning" },
  { value: "expanded", label: "Ranked + expansion", hint: "TF-IDF with corpus-based query expansion", placeholder: "neural networks" },
  { value: "rocchio", label: "Pseudo-feedback", hint: "Rocchio, top-3 results assumed relevant", placeholder: "machine learning" },
  { value: "boolean", label: "Boolean", hint: "AND, OR, NOT and parentheses", placeholder: "machine AND learning AND NOT vision" },
  { value: "wildcard", label: "Prefix / wildcard", hint: "One word with * (mach*, comput*r)", placeholder: "mach*" },
];

export const SEARCH_PAGE_SIZE = 10;

// The backend enforces this limit (SEARCHSPHERE_MAX_UPLOAD_BYTES, default 5 MB); the UI only pre-checks it.
export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;
export const ACCEPTED_UPLOAD_EXTENSIONS = [".txt", ".pdf"];

// Hard caps documented in backend/PHASE3.md (enforced server-side).
export const CRAWL_LIMITS = { maxPages: 100, maxDepth: 5 };

export const WILDCARD_EXAMPLES = ["mach*", "pro*", "secur*", "comput*r", "p*thon"];
export const BOOLEAN_EXAMPLES = [
  "machine AND learning",
  "network AND (security OR firewall)",
  "database AND NOT sql",
  "(neural OR deep) AND learning",
];

export const POLL_INTERVAL_MS = 1500;
export const TERMINAL_JOB_STATUSES = ["completed", "failed", "cancelled"];
