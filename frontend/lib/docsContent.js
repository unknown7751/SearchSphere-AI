/**
 * Static documentation content for /docs. Every statement describes the implemented system
 * (backend Phases 1-3 + this frontend); see backend/README.md, PHASE2.md and PHASE3.md for details.
 */

export const DOC_SECTIONS = [
  {
    id: "overview",
    title: "Overview",
    paragraphs: [
      "SearchSphere AI is a full-stack Information Retrieval (IR) laboratory. A FastAPI backend implements preprocessing, an inverted index, Boolean, prefix/wildcard and TF-IDF/cosine retrieval, corpus-based query expansion, Rocchio relevance feedback, evaluation metrics, document ingestion and a safe bounded web crawler. This Next.js frontend searches the corpus and exposes the intermediate calculations of every algorithm.",
    ],
  },
  {
    id: "problem",
    title: "Problem",
    paragraphs: [
      "Given a collection of unstructured text documents and a short user query, return the documents most likely to satisfy the information need, ranked by estimated relevance, and make the ranking explainable.",
    ],
  },
  {
    id: "motivation",
    title: "Motivation",
    paragraphs: [
      "Linear scanning of every document does not scale, and exact keyword matching misses morphological variants. An index plus a weighting scheme (TF-IDF) and a similarity function (cosine) is the classical, transparent solution and is the foundation that modern retrieval systems build on.",
    ],
  },
  {
    id: "objectives",
    title: "Objectives",
    bullets: [
      "Implement the core IR pipeline from scratch: tokenisation, stop-word removal, stemming, inverted index, ranking.",
      "Support Boolean, prefix/wildcard and ranked retrieval over the same index.",
      "Improve queries with expansion and Rocchio relevance feedback.",
      "Measure quality with precision, recall, F1, P@K, R@K, average precision and MAP.",
      "Grow the corpus safely by uploading files and crawling websites.",
      "Make every score explainable in the user interface.",
    ],
  },
  {
    id: "architecture",
    title: "Architecture",
    paragraphs: [
      "The browser talks only to the FastAPI service. The service owns all IR logic; the frontend collects input, calls the API and visualises the response. SQLite is the source of truth for documents; the in-memory inverted index is derived from it and rebuilt at start-up.",
    ],
    diagram: true,
  },
  {
    id: "preprocessing",
    title: "Preprocessing",
    paragraphs: [
      "Text is lower-cased and normalised, tokenised, stripped of stop words, then stemmed with the Porter stemmer (and lemmatised with WordNet for display). Index terms are the Porter stems, so “learning”, “learned” and “learns” share one posting list.",
    ],
    bullets: ["The same pipeline processes documents and queries - this symmetry is essential for matching.", "Try it: Workbench → Preprocessing."],
  },
  {
    id: "boolean",
    title: "Boolean retrieval",
    paragraphs: [
      "A query such as machine AND learning AND NOT vision is parsed into an expression tree and evaluated with set operations on postings lists: intersection (AND), union (OR) and complement (NOT). The result is an unranked set of documents.",
    ],
    bullets: ["Precise and predictable, but there is no ranking and no partial matching."],
  },
  {
    id: "index",
    title: "Inverted index",
    paragraphs: [
      "A dictionary maps each term to a postings list of (document, term frequency) pairs, sorted by document ID so intersections run by merging. Document frequency is the length of the list. Searching touches only the lists of the query terms instead of every document.",
    ],
    bullets: ["This implementation stores term frequencies; it does not store token positions, so phrase queries are not supported."],
  },
  {
    id: "tfidf",
    title: "TF-IDF",
    paragraphs: [
      "Term frequency rewards terms that occur often in a document; inverse document frequency down-weights terms that occur in many documents. The product is the weight of a term in a document vector.",
    ],
    formulas: ["tf(t, d) = raw count of t in d", "idf(t) = ln( (N + 1) / (df(t) + 1) ) + 1", "tfidf(t, d) = tf(t, d) × idf(t)"],
  },
  {
    id: "cosine",
    title: "Cosine similarity",
    paragraphs: [
      "The query and each document are vectors in term space. The cosine of the angle between them measures similarity independent of document length. Documents are ranked by decreasing cosine.",
    ],
    formulas: ["cos(q, d) = (q · d) / (‖q‖ ‖d‖)"],
  },
  {
    id: "wildcard",
    title: "Prefix / wildcard",
    paragraphs: [
      "A pattern such as mach* is a prefix lookup in the sorted dictionary (binary search); a pattern with * in the middle, such as comput*r, is matched against the dictionary and expanded to the matching terms, whose postings are then unioned. Expansion is capped to protect the server.",
    ],
  },
  {
    id: "expansion",
    title: "Query expansion",
    paragraphs: [
      "Corpus-based expansion: rank with the original query, take the top documents, and add the terms whose weight is highest in the centroid of those documents' TF-IDF vectors (present in at least two of them). Added terms get a lower weight than typed ones. No external language model or thesaurus is used.",
    ],
  },
  {
    id: "rocchio",
    title: "Rocchio",
    paragraphs: [
      "Relevance feedback moves the query vector toward the centroid of relevant documents and away from the centroid of non-relevant ones. Defaults: α = 1, β = 0.75, γ = 0.15; vectors are L2-normalised and negative weights are clipped to zero. With pseudo-feedback, the top results are assumed relevant.",
    ],
    formulas: ["q_m = α·q₀ + (β / |Dᵣ|) Σ d − (γ / |Dₙᵣ|) Σ d"],
  },
  {
    id: "evaluation",
    title: "Evaluation",
    paragraphs: ["Quality is measured against relevance judgments stored with the evaluation queries."],
    formulas: [
      "Precision = relevant retrieved / retrieved",
      "Recall = relevant retrieved / total relevant",
      "F1 = 2PR / (P + R)",
      "AP = (Σ P@k at each relevant document) / total relevant",
      "MAP = mean of AP over queries",
    ],
    bullets: ["Precision@K and Recall@K evaluate only the top K results, which matches how users read a result list."],
  },
  {
    id: "crawler",
    title: "Web crawler",
    paragraphs: [
      "A breadth-first crawler starts at a seed URL, fetches pages politely, extracts title and visible text, stores them with source_type = crawled and indexes them immediately. It is bounded: at most 100 pages, depth 5, 2 MB per response, 5 redirects and 300 seconds per job; one crawl may run at a time.",
    ],
  },
  {
    id: "security",
    title: "Security",
    bullets: [
      "SSRF protection: only http(s); host names are resolved and every address must be public (loopback, private, link-local and cloud-metadata ranges are blocked).",
      "The connection is pinned to the validated IP, so DNS cannot change between check and connect (DNS rebinding).",
      "Each redirect target goes through the full validation again.",
      "robots.txt is fetched and obeyed; if it cannot be read the site is treated as disallowed.",
      "No credentials, cookies or proxies are used, and there is no option to turn the protections off.",
      "Frontend: all backend text is rendered as text (no raw HTML) and external links are shown only for http(s) URLs.",
    ],
  },
  {
    id: "database",
    title: "Database",
    paragraphs: [
      "SQLite stores documents, evaluation queries with judgments, and crawl jobs and results. It needs no server, is a single portable file and is plenty for a coursework-scale corpus. The inverted index lives in memory and is rebuilt from SQLite, so the database stays the single source of truth.",
    ],
  },
  {
    id: "api",
    title: "API architecture",
    bullets: [
      "/api/search (+ /expanded, /rocchio, /boolean, /tolerant, /suggestions) - retrieval modes.",
      "/api/documents (list, detail, create, upload) - corpus management.",
      "/api/workbench/* - preprocessing, inverted index, incidence matrix, TF-IDF, cosine, expansion, Rocchio, evaluation walk-throughs.",
      "/api/evaluation/* - run, MAP and the stored dataset.",
      "/api/crawler/* - validate-url, start, status, results, cancel, history.",
      "Errors share one envelope: { error: { code, message, details } } and never include stack traces.",
    ],
  },
  {
    id: "testing",
    title: "Testing",
    paragraphs: [
      "The backend has an automated pytest suite (620 tests at the end of Phase 3) covering preprocessing, the index, retrieval, metrics, ingestion, the crawler's security rules (with fake network and DNS) and the HTTP API. The frontend has unit tests for the API client, formatters and search model, and component tests for the main forms.",
    ],
  },
  {
    id: "limitations",
    title: "Limitations",
    bullets: [
      "No phrase or proximity queries (positions are not stored).",
      "English only; no OCR for scanned PDFs; the crawler does not execute JavaScript.",
      "The index is in memory and rebuilt on start-up; crawl jobs do not survive a restart.",
      "Evaluation judgments come from a small, locally written dataset, so absolute scores are illustrative.",
      "Search history is not recorded, so there are no query-volume analytics.",
    ],
  },
  {
    id: "future",
    title: "Future work",
    bullets: [
      "BM25 and learned ranking; positional index for phrase search.",
      "Spelling correction (edit distance) and query suggestions.",
      "Persistent index, incremental updates and background workers for crawling.",
      "Larger public test collections and statistical significance testing.",
    ],
  },
];

export const VIVA_QUESTIONS = [
  { q: "What is an inverted index?", a: "A mapping from each term to the list of documents (with frequencies) that contain it. It lets a query read only the postings of its terms instead of scanning every document." },
  { q: "Why do we remove stop words?", a: "Words such as “the” and “of” occur in almost every document, so they carry little discriminating power while inflating index size and query cost." },
  { q: "Why use stemming?", a: "It conflates inflected forms (learning, learned, learns → learn) so a query matches documents regardless of word form, improving recall. The cost is occasional over-stemming." },
  { q: "What is TF-IDF?", a: "A weighting scheme: term frequency in the document multiplied by inverse document frequency across the corpus. Terms that are frequent here but rare elsewhere get the highest weights." },
  { q: "Why does IDF decrease for common words?", a: "IDF = ln((N+1)/(df+1)) + 1. As df grows toward N the ratio approaches 1, so the logarithm approaches 0 and the weight shrinks to its floor of 1." },
  { q: "What is cosine similarity?", a: "The cosine of the angle between the query and document vectors: dot product divided by the product of their norms. It ignores vector length, so long documents are not favoured merely for being long." },
  { q: "What is Boolean retrieval?", a: "Exact-match retrieval using AND, OR and NOT on postings lists. Documents either match or do not; there is no ranking." },
  { q: "How does prefix or wildcard search work?", a: "The dictionary is kept sorted, so a prefix like mach* is a binary-search range. A wildcard in the middle is matched against dictionary terms; the matching terms' postings are merged." },
  { q: "What is query expansion?", a: "Adding related terms to the query to fix vocabulary mismatch. Here the terms come from the top-ranked documents in this corpus, not from an external model." },
  { q: "What is Rocchio?", a: "A relevance-feedback formula: q_m = α·q0 + β·centroid(relevant) − γ·centroid(non-relevant). It moves the query toward relevant documents and away from non-relevant ones." },
  { q: "What is precision?", a: "The fraction of retrieved documents that are relevant." },
  { q: "What is recall?", a: "The fraction of all relevant documents that were retrieved." },
  { q: "What is MAP?", a: "Mean Average Precision: for each query, average the precision at the rank of each relevant document (AP), then average AP over all queries. It rewards ranking relevant documents early." },
  { q: "Why is Precision@K useful?", a: "Users read only the first few results, so quality at a fixed cut-off K reflects real experience better than precision over an arbitrarily long list." },
  { q: "How does the crawler prevent SSRF?", a: "It resolves the host name and requires every address to be public, pins the connection to that validated IP, blocks private, loopback, link-local and metadata ranges, and only allows http(s) on a small set of ports." },
  { q: "Why revalidate redirects?", a: "A public site can answer with a redirect to an internal address (for example 127.0.0.1 or the cloud metadata IP). Every hop therefore goes through the same URL, DNS, scope and robots checks." },
  { q: "Why respect robots.txt?", a: "It is the site owner's published crawling policy; honouring it is standard etiquette and reduces legal and ethical risk. If robots.txt cannot be read, the crawler assumes everything is disallowed." },
  { q: "Why use SQLite?", a: "It is serverless, a single file, transactional and built into Python, which suits a coursework-scale single-node system. The index itself is rebuilt in memory from it." },
  { q: "Why is the crawler bounded?", a: "Limits on pages, depth, size, time and queue length keep load on target sites and on this server predictable and prevent runaway crawls." },
];

export const DEMO_FLOW = [
  { step: "Search", detail: "Home → search “machine learning”. Open “Why this result?” on the first hit and read the TF, DF, IDF and cosine arithmetic." },
  { step: "Explore", detail: "Documents → open a document and show source type, metadata and content." },
  { step: "Preprocess", detail: "Workbench → Preprocessing with a sentence; walk through each stage." },
  { step: "Index", detail: "Workbench → Inverted index: look up “learning”, show the postings list and DF." },
  { step: "Boolean and wildcard", detail: "Run machine AND learning AND NOT vision, then comput*r." },
  { step: "Rank", detail: "Workbench → TF-IDF, then Cosine similarity for the same query." },
  { step: "Improve", detail: "Query expansion, then Rocchio with relevant and non-relevant documents; compare rankings before and after." },
  { step: "Evaluate", detail: "Workbench → Evaluation: single query and MAP; then Analytics to compare retrieval modes." },
  { step: "Grow the corpus", detail: "Upload a TXT/PDF and search a distinctive term; run a bounded crawl of a public page." },
  { step: "Security", detail: "Crawler → validate http://127.0.0.1/ and show it is blocked; explain SSRF protection." },
];
