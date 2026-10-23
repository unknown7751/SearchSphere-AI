# SearchSphere AI – frontend

Next.js (App Router) + React + Tailwind CSS + Lucide icons + Recharts, written in **JavaScript/JSX only** (no TypeScript).
The frontend contains **no IR logic**: it collects input, calls the FastAPI backend and visualises the intermediate
calculations the backend returns. TF-IDF, cosine similarity, Rocchio, expansion and every evaluation metric are computed
only by the backend.

## Run it

Prerequisite: **Node.js 22.22.2 or newer** (developed on 26; the app itself needs only 20.9+, the Vitest 5 / jsdom 30 test tooling needs the newer versions). Start the
backend first (see the [root README](../README.md#quick-start)), then from `frontend/`:

```powershell
npm install          # or `npm ci` for exactly the versions in package-lock.json
npm run dev          # http://localhost:3000
```

Open **http://localhost:3000** (not `127.0.0.1`: the backend's default CORS allow-list names `localhost:3000`).
Production build: `npm run build` then `npm run start` (port 3000).

| Command | Purpose |
|---|---|
| `npm run dev` | development server on port 3000 |
| `npm run build` / `npm run start` | production build / server |
| `npm run lint` | ESLint (Next.js core-web-vitals rules) |
| `npm test` | Vitest unit, hook and component tests (59) |

### Configuration

The API base URL is read from one environment variable (see `.env.example`):

```text
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Copy `.env.example` to `.env.local` to change it. When unset or empty, `http://localhost:8000` is used; a trailing slash is stripped. No secrets are involved.
`NEXT_PUBLIC_*` variables are inlined when the app is **built**, so restart `npm run dev` (or re-run `npm run build`) after changing it.
The backend allows the origin `http://localhost:3000` through CORS by default; for other origins set `SEARCHSPHERE_CORS_ORIGINS` in the backend's environment
(the backend reads real environment variables, not a `.env` file).

## Pages

| Route | Purpose |
|---|---|
| `/` | Search home: query box and the search modes the backend implements |
| `/search?q=…&mode=…&page=…` | Ranked results, latency, filters, “Why this result?” score explanation. URL is the source of truth, so searches are shareable |
| `/documents?id=…&page=…&source=…&category=…` | Corpus explorer with server-side pagination and filtering (`GET /documents` supports `source_type` and `category`) and a document detail panel |
| `/workbench?tab=…` | IR Workbench: preprocessing, Boolean, inverted index, prefix/wildcard, TF-IDF, cosine, query expansion, Rocchio, evaluation. Each section keeps its inputs and results while you visit another |
| `/analytics` | Charts built from live backend data (corpus, crawler, evaluation); honest empty state for search history |
| `/crawler` | Safe crawler control panel: validate URL, start, live job status (polling), results, history |
| `/ingest` | TXT/PDF upload with real upload progress |
| `/docs` | Technical documentation, architecture diagram, viva questions and demo flow |

Search modes: ranked (`POST /api/search`), ranked + expansion (`/search/expanded`), pseudo-feedback Rocchio
(`/search/rocchio`), Boolean (`/search/boolean`), prefix/wildcard (`/search/tolerant`).

## Backend endpoints used (the frontend only consumes existing endpoints; the full map is in the [root README](../README.md#api-endpoint-map))

| Area | Endpoints |
|---|---|
| Health | `GET /api/health` |
| Search | `POST /api/search`, `/search/expanded`, `/search/rocchio`, `/search/boolean`, `/search/tolerant`, `GET /search/suggestions` (client function only) |
| Documents | `GET /api/documents`, `GET /api/documents/{id}`, `POST /api/documents/upload` |
| Workbench | `POST /api/workbench/preprocess`, `/incidence-matrix`, `/tfidf`, `/cosine`, `/query-expansion`, `/rocchio`, `/evaluation`; `GET /workbench/inverted-index` |
| Evaluation | `GET /api/evaluation/dataset`, `POST /api/evaluation/map` |
| Crawler | `POST /api/crawler/validate-url`, `/start`, `/{id}/cancel`; `GET /api/crawler/{id}`, `/{id}/results`, `/history` |

The backend has no analytics endpoint, so `getAnalytics()` composes the dashboard from `/health`, `/documents`
(bounded to 5 pages of 100, i.e. the first 500 documents), `/crawler/history` and `/evaluation/map`. Search history is not recorded by the backend, so the
dashboard says so instead of showing invented numbers. Boolean mode is excluded from the evaluation comparison because the
stored evaluation queries are free text, not Boolean expressions.

## Structure

```text
app/          routes (server components that mount client components; Suspense where URL params are read)
components/   layout/ ui/ search/ documents/ workbench/ crawler/ analytics/ docs/
hooks/        useAsync (abort-safe loading/error state), useSearch, useCrawlJob (polling), useDebounce, ...
lib/          api.js (the only place that calls fetch/XMLHttpRequest), searchModel, formatters, analytics, constants, docsContent
tests/        Vitest tests
```

## Behaviour worth knowing

* **Stale responses.** `useAsync` aborts the previous request when a new one starts and ignores any late answer, and the search view is tagged with the
  `(query, mode)` it answers, so results for an older query are never shown under a newer one.
* **No automatic retries.** `lib/api.js` never retries; the user presses *Try again*. A failed `POST` (start crawl, cancel, upload) can therefore never run twice by itself.
  Network and timeout errors, 4xx and 5xx are mapped to short titles and messages in `describeError`.
* **Crawler polling.** `useCrawlJob` polls every 1.5 s, stops at a terminal status or after 5 consecutive failures (immediately on a 404), and clears its timer and in-flight
  request on unmount or when another job is selected. *Try again* restarts it.
* **Pages past the end** (e.g. `?page=99`) show "Page 99 does not exist" with a link to the last page instead of an empty-results message.

## Security notes

* Backend text (titles, snippets, content, URLs, error messages) is rendered as React text; `dangerouslySetInnerHTML` is never used.
* External links go through `SafeLink`, which only produces a link for `http:`/`https:` URLs (never `javascript:`, `data:`, `file:`).
* Error states show a friendly message; 5xx response text is never displayed.
* The crawler UI cannot weaken the backend's SSRF/robots.txt protections: it can only send a URL, a page limit and a depth limit. It never fetches a crawled URL itself.
* No secrets, tokens or credentials exist in the frontend; the only configuration is the public API base URL. Nothing is stored in `localStorage`/cookies.
* `next.config.mjs` adds `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` and a restrictive `Permissions-Policy`.
  No Content-Security-Policy is set: Next.js inline bootstrap scripts would require per-request nonces, and a loose CSP would give a false sense of safety.

## Known limitations

* Search result filters (source type, category) apply to the already retrieved page only: the search endpoints have no source-type filter (only `GET /documents` has one).
* Search activity is not stored by the backend, so Analytics has no query-volume or latency history. Boolean mode is absent from the evaluation comparison because the stored judged queries are free text.
* The inverted-index view states that the index holds term frequencies only, with no token positions.
* The Document explorer's category list and the Analytics charts use the first 500 documents (bounded walk over `GET /documents`).
* Upload progress covers the file transfer; text extraction and indexing happen inside the same request, so they complete together.
* `npm audit` reports 9 advisories in development-only transitive dependencies (Tailwind 3 / ESLint toolchains: `braces`, `micromatch`, `fast-glob`, `postcss-selector-parser`);
  `npm audit --omit=dev` reports none and nothing from them ships in the browser bundle. They were deliberately not "fixed" with `npm audit fix --force`, which would force a Tailwind 4 migration.
