"""Bounded, polite, SSRF-safe breadth-first web crawler.

Per URL (see PHASE3.md for the diagram)::

    validate URL + destination -> robots.txt -> fetch -> [redirect: validate + scope + robots again]
    -> content-type check -> HTML extraction -> store document -> preprocess + index -> queue links

The crawler owns three collections that make the algorithm easy to explain:

* ``queue``      - FIFO of ``(url, depth)`` still to visit (breadth-first, so results are deterministic);
* ``discovered`` - every normalised URL ever queued (a URL is queued at most once);
* ``seen_final`` - final URLs (after redirects) already processed, so two URLs redirecting to the
  same page are stored once.

Hard bounds: ``max_pages`` fetches, ``max_depth`` link hops, ``max_duration`` seconds, at most
``max_discovered`` queued URLs, same-host scope, and heuristics against URL traps.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from collections import Counter, deque
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

from app.database import crawl as crawl_db
from app.database.repository import utc_now
from app.services.html_extractor import extract_page
from app.services.http_fetcher import REDIRECT_STATUSES, FetchError, FetchResponse, Fetcher
from app.services.ingestion import content_hash
from app.services.robots import RobotsFile, RobotsPolicy
from app.services.search_engine import DuplicateContentError, SearchEngine, SourceUrlConflict
from app.services.url_validator import (
    Resolver,
    UrlRejected,
    ValidatedUrl,
    host_in_scope,
    validate_url,
)

logger = logging.getLogger("searchsphere.crawler")

HTML_TYPES = ("text/html", "application/xhtml+xml")
ROBOTS_MAX_BYTES = 512 * 1024
USER_AGENT_TOKEN = "SearchSphereBot"  # product token matched against robots.txt "User-agent" lines
# Links with these extensions are binary/non-page resources: skipped without spending a request.
SKIP_EXTENSIONS = frozenset(
    ".pdf .zip .gz .tar .tgz .rar .7z .exe .dmg .msi .iso .bin .jpg .jpeg .png .gif .svg .webp .ico .bmp .tiff "
    ".mp3 .wav .ogg .mp4 .webm .mov .avi .mkv .woff .woff2 .ttf .otf .eot .css .js .json .xml .rss .atom "
    ".doc .docx .xls .xlsx .ppt .pptx .csv".split()
)
# URL-trap heuristics (calendars, session ids, infinite path/query generators).
MAX_PATH_SEGMENTS = 12
MAX_SEGMENT_REPEATS = 2  # /a/b/a/b/a/b style loops: a segment may appear at most twice
MAX_QUERY_PARAMS = 8
MAX_QUERY_LENGTH = 256
MAX_QUERY_VARIANTS_PER_PATH = 5

SUCCESS_STATUSES = frozenset({"indexed", "updated", "unchanged", "duplicate_content"})


@dataclass(frozen=True)
class CrawlConfig:
    seed_url: str  # already normalised
    max_pages: int
    max_depth: int
    timeout: float
    include_subdomains: bool
    category: str
    delay: float
    max_response_bytes: int
    max_redirects: int
    max_duration: float
    max_discovered: int
    max_document_chars: int
    max_links_per_page: int = 200


class _Blocked(Exception):
    """Internal control flow: the URL (or a redirect hop) may not be fetched."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def is_crawl_trap(url: str) -> bool:
    """Heuristic filter for URLs that look machine-generated or endless."""
    parts = urlsplit(url)
    segments = [s for s in parts.path.split("/") if s]
    if len(segments) > MAX_PATH_SEGMENTS:
        return True
    if any(n > MAX_SEGMENT_REPEATS for n in Counter(segments).values()):
        return True
    if parts.query and (len(parts.query) > MAX_QUERY_LENGTH or parts.query.count("&") + 1 > MAX_QUERY_PARAMS):
        return True
    return False


def has_skipped_extension(url: str) -> bool:
    path = urlsplit(url).path.lower()
    dot = path.rfind(".")
    return dot > path.rfind("/") and path[dot:] in SKIP_EXTENSIONS


class Crawler:
    """Runs one crawl job to completion.  Not thread-safe; create one instance per job."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        engine: SearchEngine,
        fetcher: Fetcher,
        config: CrawlConfig,
        *,
        resolver: Resolver | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.conn = conn
        self.engine = engine
        self.fetcher = fetcher
        self.config = config
        self.resolver = resolver
        self._sleep = sleep
        self._clock = clock
        self.seed_host = urlsplit(config.seed_url).hostname or ""
        self.robots = RobotsPolicy(self._fetch_robots, USER_AGENT_TOKEN)
        self._last_request: dict[str, float] = {}
        self.attempts = 0
        self.discovered: set[str] = set()
        self.seen_final: set[str] = set()
        self._query_variants: Counter = Counter()

    # ------------------------------------------------------------------ job lifecycle
    def run(self, job_id: int) -> None:
        """Execute the job: queued -> running -> completed | cancelled | failed.  Never raises."""
        if not crawl_db.mark_running(self.conn, job_id):
            return  # cancelled before it started
        try:
            reason = self._crawl(job_id)
            crawl_db.finish_job(
                self.conn, job_id, "cancelled" if reason == "cancelled" else "completed", stop_reason=reason
            )
        except Exception:
            logger.exception("Crawl job %s failed", job_id)
            try:
                self.conn.rollback()
                crawl_db.finish_job(
                    self.conn, job_id, "failed", stop_reason="error", error="The crawl stopped because of an internal error."
                )
            except Exception:
                logger.exception("Could not record failure of crawl job %s", job_id)

    def _crawl(self, job_id: int) -> str:
        cfg = self.config
        started = self._clock()
        queue: deque[tuple[str, int]] = deque([(cfg.seed_url, 0)])
        self.discovered.add(cfg.seed_url)
        counts: Counter = Counter()
        while queue:
            if crawl_db.is_cancel_requested(self.conn, job_id):
                return "cancelled"
            if self.attempts >= cfg.max_pages:
                return "max_pages_reached"
            if self._clock() - started > cfg.max_duration:
                return "max_duration_reached"
            url, depth = queue.popleft()
            try:
                result, links = self._process(url, depth, job_id)
            except Exception:  # one bad page must never end the crawl
                logger.exception("Unexpected error while crawling %s", url)
                result, links = self._result(url, depth, "failed", "failed", error="Internal error while processing this page."), []
            crawl_db.insert_result(self.conn, job_id, result)
            counts[self._bucket(result["status"])] += 1
            if depth < cfg.max_depth:
                for link in links[: cfg.max_links_per_page]:
                    if self._enqueue(link):
                        queue.append((link, depth + 1))
            crawl_db.update_counters(
                self.conn, job_id,
                pages_discovered=len(self.discovered), pages_crawled=counts["crawled"], pages_failed=counts["failed"],
                pages_blocked=counts["blocked"], pages_skipped=counts["skipped"],
            )
        return "queue_exhausted"

    @staticmethod
    def _bucket(status: str) -> str:
        if status in SUCCESS_STATUSES:
            return "crawled"
        if status in ("blocked_by_robots", "blocked_by_security"):
            return "blocked"
        return "skipped" if status == "skipped" else "failed"

    # -------------------------------------------------------------- link management
    def _enqueue(self, link: str) -> bool:
        """Queue ``link`` if it is new, in scope and not a trap.  Cheap syntactic checks only; the
        destination is validated (DNS + IP) when the URL is actually processed."""
        if link in self.discovered or len(self.discovered) >= self.config.max_discovered:
            return False
        parts = urlsplit(link)
        if not host_in_scope(parts.hostname or "", self.seed_host, self.config.include_subdomains):
            return False
        if has_skipped_extension(link) or is_crawl_trap(link):
            return False
        if parts.query:
            key = (parts.hostname, parts.path)
            if self._query_variants[key] >= MAX_QUERY_VARIANTS_PER_PATH:
                return False
            self._query_variants[key] += 1
        self.discovered.add(link)
        return True

    # ------------------------------------------------------------------ one URL
    def _result(self, url: str, depth: int, status: str, access: str, **fields) -> dict:
        return {"url": url, "depth": depth, "status": status, "access": access, **fields}

    def _process(self, url: str, depth: int, job_id: int) -> tuple[dict, list[str]]:
        cfg = self.config
        try:
            target = validate_url(url, self.resolver)
            decision = self.robots.check(target.url)
            if not decision.allowed:
                return self._result(url, depth, "blocked_by_robots", "blocked_by_robots", error=decision.reason), []
            self.attempts += 1
            response, final = self._fetch_chain(target, accept=HTML_TYPES, max_bytes=cfg.max_response_bytes)
        except UrlRejected as exc:
            status = "blocked_by_security" if exc.is_security else "failed"
            return self._result(url, depth, status, status, error=exc.message), []
        except _Blocked as exc:
            access = exc.status if exc.status.startswith("blocked") else "allowed"
            return self._result(url, depth, exc.status, access, error=exc.message), []
        except FetchError as exc:
            return self._result(url, depth, "failed", "failed", error=exc.message), []

        base = {"final_url": final.url, "http_status": response.status_code, "content_type": response.content_type,
                "content_length": len(response.body)}
        if response.status_code >= 300:
            msg = f"HTTP {response.status_code}" + (" (redirect without a usable Location)" if response.status_code < 400 else "")
            return self._result(url, depth, "failed", "failed", error=msg, **base), []
        if response.body_skipped or response.content_type not in HTML_TYPES:
            ctype = response.content_type or "unknown"
            return self._result(url, depth, "skipped", "allowed", error=f"Unsupported content type: {ctype}", **base), []
        if final.url in self.seen_final:
            return self._result(url, depth, "skipped", "allowed", error="Redirects to a page already crawled in this job.", **base), []
        self.seen_final.add(final.url)
        self.discovered.add(final.url)

        try:
            page = extract_page(response.body, final.url, charset=response.charset, max_links=cfg.max_links_per_page)
        except Exception:
            logger.exception("HTML extraction failed for %s", final.url)
            return self._result(url, depth, "failed", "failed", error="The HTML could not be parsed.", **base), []
        links = [] if page.nofollow else page.links
        base["title"] = page.title or None

        if page.noindex:
            return self._result(url, depth, "skipped", "allowed", error="The page asks not to be indexed (meta robots noindex).", **base), links
        text = page.text
        if not text:
            return self._result(url, depth, "skipped", "allowed", error="No extractable text.", **base), links
        truncated = len(text) > cfg.max_document_chars
        if truncated:
            text = text[: cfg.max_document_chars].rstrip()
        title = page.title or final.url
        metadata = {
            "crawl_job_id": job_id,
            "content_type": response.content_type,
            "http_status": response.status_code,
            "crawled_at": utc_now(),
            "host": final.host,
            "depth": depth,
            "headings": page.headings,
            "truncated": truncated,
            **({"requested_url": url} if url != final.url else {}),
            **({"description": page.description} if page.description else {}),
        }
        try:
            doc, outcome = self.engine.store_crawled(
                self.conn, url=final.url, title=title, text=text, category=cfg.category,
                content_hash=content_hash(text), metadata=metadata,
            )
        except DuplicateContentError as exc:
            return self._result(url, depth, "duplicate_content", "allowed", document_id=exc.existing_id, indexed=True,
                                error=None, **base), links
        except SourceUrlConflict as exc:
            return self._result(url, depth, "skipped", "allowed",
                                error=f"This URL is already stored as a non-crawled document ({exc.existing_id}).", **base), links
        status = {"created": "indexed", "updated": "updated", "unchanged": "unchanged"}[outcome]
        return self._result(url, depth, status, "allowed", document_id=doc.id, indexed=doc.indexed, **base), links

    # ------------------------------------------------------------ network (security core)
    def _pace(self, url: str) -> None:
        """Politeness: wait so that requests to one host are at least ``delay`` seconds apart
        (or the robots.txt Crawl-delay, when larger)."""
        host = urlsplit(url).hostname or ""
        delay = max(self.config.delay, self.robots.cached_crawl_delay(url) or 0.0)
        last = self._last_request.get(host)
        if last is not None:
            wait = last + delay - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last_request[host] = self._clock()

    def _fetch_chain(
        self, target: ValidatedUrl, *, accept, max_bytes: int, apply_robots: bool = True, apply_scope: bool = True
    ) -> tuple[FetchResponse, ValidatedUrl]:
        """GET ``target`` and follow redirects manually.

        **Every hop is a brand-new URL** and goes through the complete pipeline again: scheme and
        port check, host-name blocklist, DNS resolution with an every-address-must-be-public rule
        (``validate_url``), crawl scope, and robots.txt.  A safe starting URL says nothing about
        where it redirects to (``public.example`` -> ``http://127.0.0.1/`` must be refused).
        The fetcher additionally pins the connection to the validated address.
        """
        hops = 0
        current = target
        while True:
            self._pace(current.url)
            response = self.fetcher.get(current.url, timeout=self.config.timeout, max_bytes=max_bytes, accept=accept)
            if response.status_code in REDIRECT_STATUSES and response.location:
                hops += 1
                if hops > self.config.max_redirects:
                    raise FetchError("too_many_redirects", f"More than {self.config.max_redirects} redirects.")
                nxt = validate_url(response.location, self.resolver, base=current.url)  # may raise UrlRejected
                if apply_scope and not host_in_scope(nxt.host, self.seed_host, self.config.include_subdomains):
                    raise _Blocked("skipped", f"Redirected outside the crawl scope ({nxt.host}).")
                if apply_robots:
                    decision = self.robots.check(nxt.url)
                    if not decision.allowed:
                        raise _Blocked("blocked_by_robots", f"Redirect target: {decision.reason}")
                current = nxt
                continue
            return response, current

    def _fetch_robots(self, robots_url: str) -> RobotsFile:
        """Fetch robots.txt through the same validated, redirect-checked path as pages."""
        try:
            target = validate_url(robots_url, self.resolver)
            response, _ = self._fetch_chain(
                target, accept=None, max_bytes=ROBOTS_MAX_BYTES, apply_robots=False, apply_scope=False
            )
        except UrlRejected as exc:
            return RobotsFile(None, problem=f"robots.txt location rejected ({exc.code}); treating the site as disallowed")
        except FetchError as exc:
            return RobotsFile(None, problem=f"robots.txt unreachable ({exc.code}); treating the site as disallowed")
        if response.status_code in REDIRECT_STATUSES:
            return RobotsFile(None, problem="robots.txt redirect without a location; treating the site as disallowed")
        if response.status_code == 200:
            try:
                body = response.body.decode(response.charset or "utf-8", errors="replace")
            except LookupError:  # unknown charset name
                body = response.body.decode("utf-8", errors="replace")
            return RobotsFile(200, body)
        return RobotsFile(response.status_code)
