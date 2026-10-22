# Phase 3 – Secure bounded web crawler

The crawler feeds the **existing** document / preprocessing / index pipeline; it adds no second
document store and no second text-normalisation system.

```
Seed URL
  ↓ normalise + validate scheme / credentials / port / host name
  ↓ resolve host → every address must be public           (SSRF check on the *destination*)
  ↓ robots.txt (cached per origin)
  ↓ fetch  (pinned to the validated IP, size/time/content-type bounded)
  ↓ redirect?  → the new URL goes through *all* the steps above again
  ↓ HTML extraction (BeautifulSoup): title, visible text, headings, links
  ↓ SearchEngine.store_crawled: documents row (source_type='crawled') + preprocess + inverted index
  ↓ queue in-scope links (breadth-first) until a bound is reached
```

## Modules

| Module | Responsibility |
|---|---|
| `services/url_validator.py` | URL normalisation, scheme/port/credential rules, host-name blocklist, IP classification, DNS resolution policy, crawl scope |
| `services/http_fetcher.py` | One safe GET: IP-pinned connection, no redirects/proxies/cookies, size + time limits, content-type allow-list |
| `services/robots.py` | robots.txt policy (stdlib `RobotFileParser`), failure policy, Crawl-delay |
| `services/html_extractor.py` | HTML → `ExtractedPage` (reuses `ingestion.normalize_text`) |
| `services/crawler.py` | The BFS algorithm, bounds, redirect loop, per-URL result recording |
| `services/crawl_manager.py` | Job creation, one-active-job rule, background entry point |
| `database/crawl.py` | SQL for `crawl_jobs` / `crawl_results` |
| `api/crawler.py`, `schemas/crawler.py` | HTTP API and Pydantic models |
| `SearchEngine.store_crawled` | Atomic insert/update + indexing of a crawled page |

## Security model

**Key idea: validating a URL string is not validating the network destination.**
`http://example.com` looks harmless, but `example.com` may resolve to `192.168.x.x`; a public
site may answer `302 → http://127.0.0.1/`. Therefore the decision is made on *resolved IP
addresses* and is repeated for every hop.

* **Schemes** – only `http` / `https`. `file:`, `ftp:`, `javascript:`, `data:`, `about:`, `chrome:`, `gopher:` … are refused (also as redirect targets).
* **Credentials** – `user:pass@host` is refused (also defeats the `http://good.com@127.0.0.1/` confusion trick). Backslashes, whitespace and control characters are refused. The crawler never sends credentials, cookies or `Referer`.
* **Ports** – only 80, 443, 8080, 8443 (so it cannot be used as a port scanner of public hosts).
* **Host names** – `localhost`, `*.localhost`, `*.local`, `*.internal`, `*.lan`, `*.home.arpa`, `metadata.google.internal`, single-label names like `intranet`, … are refused early (cheap filter only).
* **IP addresses** (`classify_ip`) – blocked: loopback (`127/8`, `::1`), unspecified, link-local (`169.254/16`, `fe80::/10`), private (`10/8`, `172.16/12`, `192.168/16`, `fc00::/7`), multicast, cloud-metadata addresses (`169.254.169.254`, `169.254.170.2`, `fd00:ec2::254`, `100.100.100.200`, `168.63.129.16`, `192.0.0.192`) and every other non-global range (CGNAT, documentation, reserved …). IPv6 addresses that merely wrap IPv4 (`::ffff:127.0.0.1`, 6to4, NAT64) are judged by the wrapped address.
* **Obfuscated IP literals** – decimal (`2130706433`), hex (`0x7f000001`), octal (`0177.0.0.1`) and short (`127.1`) forms are parsed like the OS resolver would and then classified.
* **All records must be public** – a name with one public and one private A/AAAA record is rejected.
* **Redirects** – handled manually (`allow_redirects=False`). Each `Location` is resolved against the current URL and sent through the full validation, the crawl-scope check and robots.txt before it is requested. At most 5 hops. Example outcomes are covered by tests: `public → 127.0.0.1`, `public → 169.254.169.254`, `public → name resolving to 192.168.x.x`, `public → file:///etc/passwd`, multi-hop chains, loops.
* **No proxies** – environment proxies are ignored; a proxy would become the real destination and bypass the IP checks.
* **No restriction bypass** – there is no request option to disable robots.txt or the security checks (unknown JSON fields are rejected with 422), and the crawler never solves CAPTCHAs, logs in, or retries around a 401/403.

### DNS rebinding

Naïve flow: *validate DNS → (time passes) → HTTP library resolves again → connect*. An attacker's DNS server can answer with a public IP the first time and `127.0.0.1` the second.

What is implemented: `http_fetcher` replaces urllib3's socket creation. At connect time it resolves the host, requires **all** addresses to be public (the same `resolve_destination` function used by the validator), and then connects to **that validated IP literal**. TLS still uses the original host name for SNI and certificate verification. There is no second, unvalidated lookup between check and connect. Redirect targets and robots.txt are validated and connected the same way. A test makes the DNS answer change between validation and connection and shows that no socket is opened.

Honest limits: (1) `socket.getaddrinfo` cannot be given a timeout from Python, so a hostile DNS server can delay a lookup; (2) the earlier validation and the connect-time lookup are two lookups, with the *connect-time one authoritative*; (3) this is the strongest practical protection with `requests`, not a proof of perfect SSRF prevention – the server should additionally run with network-level egress filtering when deployed beyond a coursework setting.

## robots.txt policy

Fetched once per origin (scheme + host + port) through the same validated path, then cached. Parsed with `urllib.robotparser`; user-agent token `SearchSphereBot`.

| robots.txt result | Decision |
|---|---|
| 200 | rules apply |
| 404 / 410 / other 4xx except 401, 403 | no rules → allowed |
| 401, 403 | restricted → **everything disallowed** |
| 5xx, timeout, connection error, oversized (>512 KB), unsafe redirect | unknown → **everything disallowed** |

`Crawl-delay` is honoured (capped at 5 s). Per page the result is one of `allowed`, `blocked_by_robots`, `blocked_by_security`, `failed` (field `access`); the finer outcome is in `status`. `<meta name="robots" content="noindex">` pages are not stored and `nofollow` pages' links are not followed.

## Bounds and scope

| Limit | Default / hard cap |
|---|---|
| `max_pages` – page fetches (robots.txt not counted) | 10 / 100 |
| `max_depth` – link hops from the seed (0 = seed only) | 2 / 5 |
| `timeout_seconds` – per request (connect ≤ 5 s; whole download ≤ 2× timeout) | 10 / 30 |
| Response size (decompressed) | 2 MB (`SEARCHSPHERE_CRAWLER_MAX_BYTES`) |
| Redirects per URL | 5 |
| Job duration | 300 s |
| Queued URLs per job | 1000; links taken per page: 200 |
| Delay between requests to a host | 0.5 s (or robots Crawl-delay if larger) |
| Concurrent crawls | 1 (a second `start` returns 409) |

**Scope (default):** the seed's host only; `www.` is treated as equivalent to the bare host. `include_subdomains: true` additionally follows subdomains of the seed host (never sibling sites). Links to other sites are not queued; a redirect that leaves the scope is recorded as `skipped`.

**Traps:** URLs with >12 path segments, a segment repeated more than twice, >8 query parameters or a query longer than 256 characters are not followed; at most 5 different query strings per path are crawled; links to binary/static extensions (`.pdf .zip .png .css .js …`) are never requested.

**URL identity:** scheme/host lower-cased, default port, fragment, `.`/`..` segments and percent-encoding case normalised; empty path → `/`. Query order, path case and the trailing slash of non-root paths are **kept**, because collapsing them can merge different pages.

**Content types:** only `text/html` and `application/xhtml+xml` are read (checked from the headers *before* the body is downloaded); everything else is `skipped`.

## Storage and duplicates

Crawled pages are rows in `documents` (`source_type='crawled'`, `file_type='html'`, `source_url` = final normalised URL). Crawl provenance is in the existing `metadata_json` column (no change to `documents`): `crawl_job_id`, `content_type`, `http_status`, `crawled_at`, `host`, `depth`, `headings`, `description`, `truncated`, and `requested_url` when a redirect occurred. Text is limited to `SEARCHSPHERE_MAX_DOCUMENT_CHARS` (truncated, flagged).

| Situation | Result `status` |
|---|---|
| new URL | `indexed` |
| same URL, same text | `unchanged` (metadata refreshed, **no re-indexing**) |
| same URL, changed text | `updated` (row rewritten, index entry replaced atomically) |
| different URL, identical text | `duplicate_content` (points at the existing `document_id`, nothing stored) |
| URL already held by a user/seed document | `skipped` (never overwritten) |

Two URLs redirecting to the same page are stored once.

## Database (backward compatible: new tables only)

* `crawl_jobs` – `id, seed_url, status(queued|running|completed|failed|cancelled), max_pages, max_depth, timeout_seconds, include_subdomains, category, pages_discovered, pages_crawled, pages_failed, pages_blocked, pages_skipped, cancel_requested, stop_reason, error, created_at, started_at, completed_at`; index on `status`.
* `crawl_results` – `id, job_id → crawl_jobs (CASCADE), url, final_url, title, status, access, depth, http_status, content_type, content_length, document_id → documents (SET NULL), indexed, error, crawled_at`; `UNIQUE(job_id, url)`; indexes on `(job_id, id)` and `document_id`.

`stop_reason`: `queue_exhausted`, `max_pages_reached`, `max_duration_reached`, `cancelled`, `error`.

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/crawler/start` | validate seed (incl. DNS), create job, crawl in background → `202` + job |
| `GET /api/crawler/{job_id}` | status, counters, `progress`, `error_count`, last 5 errors |
| `GET /api/crawler/{job_id}/results?page&page_size&status` | per-URL outcomes |
| `POST /api/crawler/{job_id}/cancel` | queued → cancelled at once; running → flagged, stops at next page boundary; finished → `409` |
| `POST /api/crawler/validate-url` | dry-run of the URL policy (no fetch; resolved IPs are never returned) |
| `GET /api/crawler/history?page&page_size` | jobs, newest first |

Start body: `{"url", "max_pages"=10, "max_depth"=2, "timeout_seconds"=10, "include_subdomains"=false, "category"="Crawled"}`. Rejections: `422 validation_error` (bad numbers, unknown fields), `400 url_blocked` (security: `details.reason` e.g. `private_address`, `metadata_endpoint`, `unsupported_scheme`), `400 invalid_url`, `409 crawl_in_progress`.

Search integration: `POST /api/search` (and Boolean/tolerant results) now include `source_type` (`seed|user|crawled`) and `source_url` per result; `GET /api/documents/{id}` exposes the crawl metadata.

## Execution model and limitations

* Jobs run through FastAPI `BackgroundTasks` (a worker thread in the server process). This is **not** a distributed queue: jobs do not survive a restart (unfinished jobs are marked `failed` at start-up). State is in SQLite, so any process can read it.
* Cancellation is cooperative: the page being fetched when the flag is set still completes.
* JavaScript is not executed; client-rendered pages yield little or no text.
* The standard-library robots parser does not understand `*`/`$` wildcards inside paths and applies the first matching rule in file order (RFC 9309 uses the longest match); this errs towards not crawling when an `Allow` follows a broader `Disallow`.
* No CAPTCHA/login handling, no PDF/binary crawling, no sitemap support, no incremental `If-Modified-Since` (re-crawls re-download and compare a content hash).
* Content hash deduplication is exact (normalised text), not near-duplicate detection.
* DNS limitations as described above.

## Tests

`pytest` runs all phases. Crawler tests use a fake fetcher and fake DNS (no internet): `test_url_validator.py` (normalisation, IP classes, obfuscated literals, hostname→private resolution), `test_html_extractor.py`, `test_robots.py`, `test_crawler.py` (depth, page limit, loops, scope, traps, robots, redirects to loopback/metadata/private/`file:`, status codes, content types, duplicates, re-crawl, cancellation, politeness delay), `test_http_fetcher.py` (real `requests`/urllib3 stack against a local server without relaxing the SSRF policy: IP pinning, size/timeout/compression limits, DNS-rebinding scenario), `test_crawler_api.py` (endpoints, validation, crawl → search integration).
