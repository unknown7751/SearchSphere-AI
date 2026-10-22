import sqlite3

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request

from app.api.deps import get_conn
from app.core.errors import AppError
from app.database import crawl as crawl_db
from app.schemas.crawler import (
    CrawlHistory,
    CrawlJob,
    CrawlJobDetail,
    CrawlResultsPage,
    CrawlStartRequest,
    ResultStatus,
    ValidateUrlRequest,
    ValidateUrlResponse,
)
from app.services.crawl_manager import CrawlManager, progress_of
from app.services.url_validator import UrlRejected, normalize_url, validate_url

router = APIRouter(prefix="/crawler", tags=["crawler"])


def get_manager(request: Request) -> CrawlManager:
    return request.app.state.crawl_manager


def _job_view(job: dict) -> dict:
    return {**job, "progress": progress_of(job)}


def _require_job(conn: sqlite3.Connection, job_id: int) -> dict:
    job = crawl_db.get_job(conn, job_id)
    if job is None:
        raise AppError(404, "crawl_job_not_found", f"Crawl job {job_id} does not exist.")
    return job


@router.post("/validate-url", response_model=ValidateUrlResponse)
def validate_crawl_url(body: ValidateUrlRequest, manager: CrawlManager = Depends(get_manager)):
    """Dry-run the crawler's URL policy (scheme, host name, DNS resolution, public-address check) without fetching anything."""
    try:
        normalized = normalize_url(body.url)
        validate_url(normalized, manager.resolver)
    except UrlRejected as exc:
        status = "blocked_by_security" if exc.is_security else "invalid"
        return {"url": body.url, "normalized_url": None, "allowed": False, "status": status, "reason": exc.code, "message": exc.message}
    return {"url": body.url, "normalized_url": normalized, "allowed": True, "status": "allowed"}


@router.post("/start", response_model=CrawlJob, status_code=202)
def start_crawl(
    body: CrawlStartRequest,
    background: BackgroundTasks,
    manager: CrawlManager = Depends(get_manager),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Validate the seed (including where its host name resolves), create a ``queued`` job and crawl in the background."""
    job = manager.create_job(
        conn, url=body.url, max_pages=body.max_pages, max_depth=body.max_depth, timeout_seconds=body.timeout_seconds,
        include_subdomains=body.include_subdomains, category=body.category,
    )
    background.add_task(manager.run, job["job_id"])
    return _job_view(job)


@router.get("/history", response_model=CrawlHistory)
def crawl_history(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), conn: sqlite3.Connection = Depends(get_conn)
):
    jobs, total = crawl_db.list_jobs(conn, limit=page_size, offset=(page - 1) * page_size)
    return {"items": [_job_view(j) for j in jobs], "total": total, "page": page, "page_size": page_size}


@router.get("/{job_id}", response_model=CrawlJobDetail)
def crawl_status(job_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    job = _require_job(conn, job_id)
    errors, total = crawl_db.recent_errors(conn, job_id)
    return {**_job_view(job), "error_count": total, "recent_errors": errors}


@router.get("/{job_id}/results", response_model=CrawlResultsPage)
def crawl_results(
    job_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: ResultStatus | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
):
    _require_job(conn, job_id)
    items, total = crawl_db.list_results(conn, job_id, limit=page_size, offset=(page - 1) * page_size, status=status)
    return {"job_id": job_id, "items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/{job_id}/cancel", response_model=CrawlJob)
def cancel_crawl(job_id: int, manager: CrawlManager = Depends(get_manager), conn: sqlite3.Connection = Depends(get_conn)):
    """Cancel a queued job immediately; a running job stops at the next page boundary (poll its status)."""
    _require_job(conn, job_id)
    if manager.cancel(conn, job_id) is None:
        raise AppError(409, "job_not_cancellable", "The crawl job has already finished.")
    return _job_view(crawl_db.get_job(conn, job_id))
