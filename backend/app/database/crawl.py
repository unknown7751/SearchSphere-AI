"""Persistence for crawl jobs and per-URL results.  All SQL is parameterised; each function commits."""
from __future__ import annotations

import sqlite3

from app.database.repository import utc_now

ACTIVE_STATUSES = ("queued", "running")
_COUNTERS = ("pages_discovered", "pages_crawled", "pages_failed", "pages_blocked", "pages_skipped")
RESULT_COLUMNS = (
    "id, job_id, url, final_url, title, status, access, depth, http_status, content_type, content_length,"
    " document_id, indexed, error, crawled_at"
)


def create_job(
    conn: sqlite3.Connection,
    *,
    seed_url: str,
    max_pages: int,
    max_depth: int,
    timeout_seconds: float,
    include_subdomains: bool,
    category: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO crawl_jobs (seed_url, status, max_pages, max_depth, timeout_seconds, include_subdomains, category,"
        " created_at) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?)",
        (seed_url, max_pages, max_depth, timeout_seconds, int(include_subdomains), category, utc_now()),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_job(conn: sqlite3.Connection, job_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM crawl_jobs WHERE id = ?", (job_id,)).fetchone()
    return _job(row) if row else None


def _job(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["job_id"] = d.pop("id")
    d["include_subdomains"] = bool(d["include_subdomains"])
    d["cancel_requested"] = bool(d["cancel_requested"])
    return d


def list_jobs(conn: sqlite3.Connection, *, limit: int, offset: int) -> tuple[list[dict], int]:
    total = conn.execute("SELECT COUNT(*) FROM crawl_jobs").fetchone()[0]
    rows = conn.execute("SELECT * FROM crawl_jobs ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    return [_job(r) for r in rows], total


def has_active_job(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM crawl_jobs WHERE status IN ('queued', 'running') LIMIT 1").fetchone() is not None


def mark_running(conn: sqlite3.Connection, job_id: int) -> bool:
    """queued -> running.  False when the job was cancelled (or already started) in the meantime."""
    cur = conn.execute(
        "UPDATE crawl_jobs SET status = 'running', started_at = ? WHERE id = ? AND status = 'queued'", (utc_now(), job_id)
    )
    conn.commit()
    return cur.rowcount == 1


def finish_job(conn: sqlite3.Connection, job_id: int, status: str, *, stop_reason: str | None, error: str | None = None) -> None:
    """running -> terminal state.  Guarded so it can never overwrite an already-terminal state."""
    conn.execute(
        "UPDATE crawl_jobs SET status = ?, stop_reason = ?, error = ?, completed_at = ? WHERE id = ? AND status = 'running'",
        (status, stop_reason, error, utc_now(), job_id),
    )
    conn.commit()


def request_cancel(conn: sqlite3.Connection, job_id: int) -> str | None:
    """Cancel a job.  Queued jobs are cancelled immediately; a running job is flagged and its worker
    stops at the next page boundary.  Returns the resulting action or None if the job is finished."""
    cur = conn.execute(
        "UPDATE crawl_jobs SET status = 'cancelled', stop_reason = 'cancelled', completed_at = ?"
        " WHERE id = ? AND status = 'queued'",
        (utc_now(), job_id),
    )
    if cur.rowcount:
        conn.commit()
        return "cancelled"
    cur = conn.execute("UPDATE crawl_jobs SET cancel_requested = 1 WHERE id = ? AND status = 'running'", (job_id,))
    conn.commit()
    return "cancel_requested" if cur.rowcount else None


def is_cancel_requested(conn: sqlite3.Connection, job_id: int) -> bool:
    row = conn.execute("SELECT cancel_requested, status FROM crawl_jobs WHERE id = ?", (job_id,)).fetchone()
    return row is None or bool(row["cancel_requested"]) or row["status"] != "running"


def update_counters(conn: sqlite3.Connection, job_id: int, **counters: int) -> None:
    assert set(counters) <= set(_COUNTERS)  # column names come from the constant above, never from users
    sets = ", ".join(f"{k} = ?" for k in counters)
    conn.execute(f"UPDATE crawl_jobs SET {sets} WHERE id = ?", [*counters.values(), job_id])
    conn.commit()


def interrupt_unfinished(conn: sqlite3.Connection) -> int:
    """Called at start-up: jobs left queued/running by a previous process can never finish."""
    cur = conn.execute(
        "UPDATE crawl_jobs SET status = 'failed', stop_reason = 'error', error = ?, completed_at = ?"
        " WHERE status IN ('queued', 'running')",
        ("The server stopped before the crawl finished.", utc_now()),
    )
    conn.commit()
    return cur.rowcount


def insert_result(conn: sqlite3.Connection, job_id: int, r: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO crawl_results (job_id, url, final_url, title, status, access, depth, http_status,"
        " content_type, content_length, document_id, indexed, error, crawled_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            job_id, r["url"], r.get("final_url"), r.get("title"), r["status"], r["access"], r["depth"],
            r.get("http_status"), r.get("content_type"), r.get("content_length"), r.get("document_id"),
            int(bool(r.get("indexed"))), r.get("error"), utc_now(),
        ),
    )
    conn.commit()


def list_results(
    conn: sqlite3.Connection, job_id: int, *, limit: int, offset: int, status: str | None = None
) -> tuple[list[dict], int]:
    where, params = "WHERE job_id = ?", [job_id]
    if status:
        where += " AND status = ?"
        params.append(status)
    total = conn.execute(f"SELECT COUNT(*) FROM crawl_results {where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT {RESULT_COLUMNS} FROM crawl_results {where} ORDER BY id LIMIT ? OFFSET ?", [*params, limit, offset]
    ).fetchall()
    return [_result(r) for r in rows], total


def recent_errors(conn: sqlite3.Connection, job_id: int, limit: int = 5) -> tuple[list[dict], int]:
    """Latest results that carry an error message, plus the total number of such results."""
    where = "job_id = ? AND error IS NOT NULL"
    total = conn.execute(f"SELECT COUNT(*) FROM crawl_results WHERE {where}", (job_id,)).fetchone()[0]
    rows = conn.execute(
        f"SELECT url, status, access, http_status, error FROM crawl_results WHERE {where} ORDER BY id DESC LIMIT ?",
        (job_id, limit),
    ).fetchall()
    return [dict(r) for r in rows], total


def _result(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["indexed"] = bool(d["indexed"])
    return d
