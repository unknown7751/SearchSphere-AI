# SearchSphere AI – frontend (Phase 4)

Next.js (App Router) + React + Tailwind CSS + Lucide icons + Recharts, written in **JavaScript/JSX only** (no TypeScript).
The frontend contains **no IR logic**: it collects input, calls the FastAPI backend and visualises the intermediate
calculations the backend returns. TF-IDF, cosine similarity, Rocchio, expansion and every evaluation metric are computed
only by the backend.

## Run it

Start the backend first (see `../backend/README.md`), then from `frontend/`:

```powershell
npm install
npm run dev          # http://localhost:3000
```

Production build: `npm run build` then `npm run start`.

| Command | Purpose |
|---|---|
| `npm run dev` | development server on port 3000 |
| `npm run build` / `npm run start` | production build / server |
| `npm run lint` | ESLint (Next.js core-web-vitals rules) |
| `npm test` | Vitest unit and component tests |

### Configuration

The API base URL is read from one environment variable (see `.env.example`):

```text
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Copy `.env.example` to `.env.local` to change it. When unset, `http://localhost:8000` is used. No secrets are involved.
The backend allows the origin `http://localhost:3000` through CORS by default (`SEARCHSPHERE_CORS_ORIGINS` in the backend).

## Pages

| Route | Purpose |
|---|---|
| `/` | Search home: query box and the search modes the backend implements |
| `/search?q=…&mode=…&page=…` | Ranked results, latency, filters, “Why this result?” score explanation. URL is the source of truth, so searches are shareable |
| `/documents?id=…&page=…&source=…&category=…` | Corpus explorer with server-side pagination and a document detail panel |
| `/workbench?tab=…` | IR Workbench: preprocessing, Boolean, inverted index, prefix/wildcard, TF-IDF, cosine, query expansion, Rocchio, evaluation |
| `/analytics` | Charts built from live backend data (corpus, crawler, evaluation); honest empty state for search history |
| `/crawler` | Safe crawler control panel: validate URL, start, live job status (polling), results, history |
| `/ingest` | TXT/PDF upload with real upload progress |
| `/docs` | Technical documentation, architecture diagram, viva questions and demo flow |

Search modes: ranked (`POST /api/search`), ranked + expansion (`/search/expanded`), pseudo-feedback Rocchio
(`/search/rocchio`), Boolean (`/search/boolean`), prefix/wildcard (`/search/tolerant`).

## Backend endpoints used (all existing; **no backend change was needed for Phase 4**)

| Area | Endpoints |
|---|---|
| Health | `GET /api/health` |
| Search | `POST /api/search`, `/search/expanded`, `/search/rocchio`, `/search/boolean`, `/search/tolerant`, `GET /search/suggestions` (client function only) |
| Documents | `GET /api/documents`, `GET /api/documents/{id}`, `POST /api/documents/upload` |
| Workbench | `POST /api/workbench/preprocess`, `/incidence-matrix`, `/tfidf`, `/cosine`, `/query-expansion`, `/rocchio`, `/evaluation`; `GET /workbench/inverted-index` |
| Evaluation | `GET /api/evaluation/dataset`, `POST /api/evaluation/map` |
| Crawler | `POST /api/crawler/validate-url`, `/start`, `/{id}/cancel`; `GET /api/crawler/{id}`, `/{id}/results`, `/history` |

The backend has no analytics endpoint, so `getAnalytics()` composes the dashboard from `/health`, `/documents`
(bounded to 5 pages of 100), `/crawler/history` and `/evaluation/map`. Search history is not recorded by the backend, so the
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

## Security notes

* Backend text (titles, snippets, content, URLs, error messages) is rendered as React text; `dangerouslySetInnerHTML` is never used.
* External links go through `SafeLink`, which only produces a link for `http:`/`https:` URLs (never `javascript:`, `data:`, `file:`).
* Error states show a friendly message; 5xx response text is never displayed.
* The crawler UI cannot weaken the backend's SSRF/robots.txt protections: it can only send a URL, a page limit and a depth limit.

## Known limitations

* Search filters (source type, category) apply to the already retrieved page only; the search endpoints have no such filters.
* Upload progress covers the file transfer; text extraction and indexing happen inside the same request, so they complete together.
* `npm audit` reports advisories in development-only transitive dependencies (Tailwind 3 / ESLint toolchains); none ship in the browser bundle.
