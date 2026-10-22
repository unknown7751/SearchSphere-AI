"""SQLite schema. ``init_db`` is idempotent: every statement uses IF NOT EXISTS and columns
added after Phase 1 are applied to older databases by :func:`_migrate_documents`."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id   TEXT UNIQUE,                       -- stable ID of seed/crawled documents, e.g. 'seed-007'
    title         TEXT NOT NULL CHECK (length(trim(title)) > 0),
    text          TEXT NOT NULL CHECK (length(trim(text)) > 0),
    category      TEXT NOT NULL CHECK (length(trim(category)) > 0),
    source_type   TEXT NOT NULL CHECK (source_type IN ('seed', 'user', 'crawled')),
    source_url    TEXT,
    published_at  TEXT,                              -- ISO date when known
    ingested_at   TEXT NOT NULL,                     -- ISO-8601 UTC timestamp (created_at)
    word_count    INTEGER NOT NULL CHECK (word_count >= 0),
    indexed       INTEGER NOT NULL DEFAULT 0 CHECK (indexed IN (0, 1))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_documents_source_url ON documents(source_url) WHERE source_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_documents_category    ON documents(category);
CREATE INDEX IF NOT EXISTS ix_documents_source_type ON documents(source_type);
CREATE INDEX IF NOT EXISTS ix_documents_indexed     ON documents(indexed);

CREATE TABLE IF NOT EXISTS index_metadata (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Phase 2: evaluation dataset (queries + binary relevance judgments).
CREATE TABLE IF NOT EXISTS evaluation_queries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text  TEXT NOT NULL UNIQUE CHECK (length(trim(query_text)) > 0),
    description TEXT
);
CREATE TABLE IF NOT EXISTS relevance_judgments (
    query_id    INTEGER NOT NULL REFERENCES evaluation_queries(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    relevance   INTEGER NOT NULL DEFAULT 1 CHECK (relevance IN (0, 1)),
    PRIMARY KEY (query_id, document_id)
);
CREATE INDEX IF NOT EXISTS ix_judgments_document ON relevance_judgments(document_id);

-- Phase 3: web crawler. Crawled pages are ordinary rows of ``documents`` (source_type='crawled');
-- these tables only hold the job bookkeeping and the per-URL outcome.
CREATE TABLE IF NOT EXISTS crawl_jobs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    seed_url           TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'queued'
                       CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    max_pages          INTEGER NOT NULL CHECK (max_pages > 0),
    max_depth          INTEGER NOT NULL CHECK (max_depth >= 0),
    timeout_seconds    REAL NOT NULL CHECK (timeout_seconds > 0),
    include_subdomains INTEGER NOT NULL DEFAULT 0 CHECK (include_subdomains IN (0, 1)),
    category           TEXT NOT NULL,
    pages_discovered   INTEGER NOT NULL DEFAULT 0,
    pages_crawled      INTEGER NOT NULL DEFAULT 0,   -- fetched and stored / refreshed / recognised as duplicate
    pages_failed       INTEGER NOT NULL DEFAULT 0,
    pages_blocked      INTEGER NOT NULL DEFAULT 0,   -- blocked by robots.txt or by the security policy
    pages_skipped      INTEGER NOT NULL DEFAULT 0,   -- unsupported content, noindex, out-of-scope redirect ...
    cancel_requested   INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
    stop_reason        TEXT,
    error              TEXT,
    created_at         TEXT NOT NULL,
    started_at         TEXT,
    completed_at       TEXT
);
CREATE INDEX IF NOT EXISTS ix_crawl_jobs_status ON crawl_jobs(status);

CREATE TABLE IF NOT EXISTS crawl_results (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id         INTEGER NOT NULL REFERENCES crawl_jobs(id) ON DELETE CASCADE,
    url            TEXT NOT NULL,                    -- normalised URL that was queued
    final_url      TEXT,                             -- after redirects
    title          TEXT,
    status         TEXT NOT NULL,                    -- indexed|updated|unchanged|duplicate_content|blocked_by_robots|
                                                     -- blocked_by_security|skipped|failed
    access         TEXT NOT NULL,                    -- allowed|blocked_by_robots|blocked_by_security|failed
    depth          INTEGER NOT NULL,
    http_status    INTEGER,
    content_type   TEXT,
    content_length INTEGER,                          -- bytes downloaded
    document_id    INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    indexed        INTEGER NOT NULL DEFAULT 0 CHECK (indexed IN (0, 1)),
    error          TEXT,
    crawled_at     TEXT NOT NULL,
    UNIQUE (job_id, url)
);
CREATE INDEX IF NOT EXISTS ix_crawl_results_job      ON crawl_results(job_id, id);
CREATE INDEX IF NOT EXISTS ix_crawl_results_document ON crawl_results(document_id);
"""

# Phase 2 metadata columns for ingested files (added with ALTER TABLE on pre-existing databases).
DOCUMENT_COLUMNS_V2 = {
    "file_type": "TEXT",       # 'txt', 'pdf' (NULL for documents created through the JSON API / seed)
    "source_name": "TEXT",     # original file name
    "updated_at": "TEXT",      # ISO-8601 UTC; equals ingested_at until the document is edited
    "content_hash": "TEXT",    # SHA-256 of the normalised text, used for duplicate detection
    "metadata_json": "TEXT",   # extra extracted metadata (PDF page count, author, ...) as JSON
}


def _migrate_documents(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
    for column, ddl in DOCUMENT_COLUMNS_V2.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE documents ADD COLUMN {column} {ddl}")  # names come from the constant above
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_documents_content_hash ON documents(content_hash) WHERE content_hash IS NOT NULL"
    )


def init_db(conn: sqlite3.Connection) -> None:
    with conn:
        conn.executescript(SCHEMA)
        _migrate_documents(conn)
