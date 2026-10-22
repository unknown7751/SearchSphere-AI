"""Creates, runs and cancels crawl jobs.  Job state lives in SQLite, never only in memory.

Execution model: the API creates the job row (``queued``) and schedules :meth:`CrawlManager.run`
with FastAPI ``BackgroundTasks`` (a worker thread in the web server process).  That is a
lightweight convenience, *not* a distributed job queue: jobs do not survive a server restart
(``interrupt_unfinished`` marks them failed at start-up) and only one crawl may be active at a
time, which keeps load on target sites and on SQLite predictable.
"""
from __future__ import annotations

import logging
import threading

from app.core.config import Settings
from app.core.errors import AppError
from app.database import crawl as crawl_db
from app.database.connection import connect
from app.services.crawler import Crawler, CrawlConfig
from app.services.http_fetcher import Fetcher, SafeFetcher
from app.services.search_engine import SearchEngine
from app.services.url_validator import Resolver, UrlRejected, validate_url

logger = logging.getLogger("searchsphere.crawler")


class CrawlManager:
    def __init__(
        self,
        settings: Settings,
        engine: SearchEngine,
        *,
        fetcher: Fetcher | None = None,
        resolver: Resolver | None = None,
        sleep=None,
    ):
        """``fetcher`` / ``resolver`` / ``sleep`` exist so tests can run the full crawler
        deterministically without network access; production uses the defaults."""
        self.settings = settings
        self.engine = engine
        self._fetcher = fetcher
        self.resolver = resolver
        self._sleep = sleep
        self._start_lock = threading.Lock()

    def reject_url(self, url: str):
        """Validate a URL *and its resolved destination*.  Returns the ValidatedUrl or raises AppError."""
        try:
            return validate_url(url, self.resolver)
        except UrlRejected as exc:
            code = "url_blocked" if exc.is_security else "invalid_url"
            raise AppError(400, code, exc.message, {"reason": exc.code}) from exc

    def create_job(self, conn, *, url: str, max_pages: int, max_depth: int, timeout_seconds: float,
                   include_subdomains: bool, category: str) -> dict:
        target = self.reject_url(url)
        with self._start_lock:
            if crawl_db.has_active_job(conn):
                raise AppError(409, "crawl_in_progress", "Another crawl is queued or running; wait for it to finish or cancel it.")
            job_id = crawl_db.create_job(
                conn, seed_url=target.url, max_pages=max_pages, max_depth=max_depth, timeout_seconds=timeout_seconds,
                include_subdomains=include_subdomains, category=category,
            )
        return crawl_db.get_job(conn, job_id)

    def cancel(self, conn, job_id: int) -> str | None:
        return crawl_db.request_cancel(conn, job_id)

    def run(self, job_id: int) -> None:
        """Background entry point: opens its own database connection and runs the crawl."""
        conn = connect(self.settings.database_path)
        fetcher = self._fetcher or SafeFetcher(self.settings.crawler_user_agent, self.resolver)
        try:
            job = crawl_db.get_job(conn, job_id)
            if job is None:
                return
            config = CrawlConfig(
                seed_url=job["seed_url"],
                max_pages=job["max_pages"],
                max_depth=job["max_depth"],
                timeout=job["timeout_seconds"],
                include_subdomains=job["include_subdomains"],
                category=job["category"],
                delay=self.settings.crawler_request_delay,
                max_response_bytes=self.settings.crawler_max_response_bytes,
                max_redirects=self.settings.crawler_max_redirects,
                max_duration=self.settings.crawler_max_duration,
                max_discovered=self.settings.crawler_max_discovered,
                max_document_chars=self.settings.max_document_chars,
            )
            kwargs = {"resolver": self.resolver}
            if self._sleep is not None:
                kwargs["sleep"] = self._sleep
            Crawler(conn, self.engine, fetcher, config, **kwargs).run(job_id)
        except Exception:
            logger.exception("Crawl job %s could not run", job_id)
        finally:
            if self._fetcher is None:
                fetcher.close()
            conn.close()


def progress_of(job: dict) -> float:
    """Fraction of discovered URLs that have been processed; 1.0 for a job that ended normally."""
    if job["status"] in ("completed", "cancelled"):
        return 1.0
    processed = job["pages_crawled"] + job["pages_failed"] + job["pages_blocked"] + job["pages_skipped"]
    return round(min(1.0, processed / job["pages_discovered"]), 4) if job["pages_discovered"] else 0.0

