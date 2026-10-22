"""SQLite schema. ``init_db`` is idempotent (every statement uses IF NOT EXISTS)."""
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
    ingested_at   TEXT NOT NULL,                     -- ISO-8601 UTC timestamp
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
"""


def init_db(conn: sqlite3.Connection) -> None:
    with conn:
        conn.executescript(SCHEMA)
