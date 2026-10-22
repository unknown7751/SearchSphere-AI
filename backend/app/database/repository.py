"""Document persistence. All SQL is parameterised; callers own transaction boundaries."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Iterator, Sequence

from app.models.document import Document

_WORD = re.compile(r"\w+", re.UNICODE)
_COLUMNS = "id, external_id, title, text, category, source_type, source_url, published_at, ingested_at, word_count, indexed"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def count_words(text: str) -> int:
    return len(_WORD.findall(text))


def _to_doc(row: sqlite3.Row) -> Document:
    d = dict(row)
    d["indexed"] = bool(d["indexed"])
    return Document(**d)


def insert_document(
    conn: sqlite3.Connection,
    *,
    title: str,
    text: str,
    category: str,
    source_type: str,
    source_url: str | None = None,
    published_at: str | None = None,
    external_id: str | None = None,
) -> int:
    """Insert a document (not yet indexed) and return its ID. Does not commit."""
    cur = conn.execute(
        "INSERT INTO documents (external_id, title, text, category, source_type, source_url, published_at,"
        " ingested_at, word_count, indexed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
        (external_id, title, text, category, source_type, source_url, published_at, utc_now(), count_words(text)),
    )
    return int(cur.lastrowid)


def get_document(conn: sqlite3.Connection, doc_id: int) -> Document | None:
    row = conn.execute(f"SELECT {_COLUMNS} FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return _to_doc(row) if row else None


def get_documents(conn: sqlite3.Connection, ids: Sequence[int]) -> dict[int, Document]:
    """Fetch several documents by ID (chunked to respect SQLite's variable limit)."""
    out: dict[int, Document] = {}
    ids = list(dict.fromkeys(ids))
    for i in range(0, len(ids), 500):
        chunk = ids[i : i + 500]
        marks = ",".join("?" * len(chunk))
        for row in conn.execute(f"SELECT {_COLUMNS} FROM documents WHERE id IN ({marks})", chunk):
            out[row["id"]] = _to_doc(row)
    return out


def list_documents(
    conn: sqlite3.Connection,
    *,
    page: int = 1,
    page_size: int = 20,
    category: str | None = None,
    source_type: str | None = None,
) -> tuple[list[Document], int]:
    where, params = [], []
    if category:
        where.append("category = ?")
        params.append(category)
    if source_type:
        where.append("source_type = ?")
        params.append(source_type)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM documents {clause}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM documents {clause} ORDER BY id LIMIT ? OFFSET ?",
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    return [_to_doc(r) for r in rows], total


def iter_all_documents(conn: sqlite3.Connection) -> Iterator[Document]:
    for row in conn.execute(f"SELECT {_COLUMNS} FROM documents ORDER BY id"):
        yield _to_doc(row)


def delete_document(conn: sqlite3.Connection, doc_id: int) -> bool:
    return conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,)).rowcount > 0


def set_indexed(conn: sqlite3.Connection, doc_ids: Sequence[int] | None, indexed: bool) -> None:
    """Set the indexed flag for the given IDs (or for every document when ``doc_ids`` is None)."""
    if doc_ids is None:
        conn.execute("UPDATE documents SET indexed = ?", (int(indexed),))
        return
    for i in range(0, len(doc_ids), 500):
        chunk = list(doc_ids[i : i + 500])
        marks = ",".join("?" * len(chunk))
        conn.execute(f"UPDATE documents SET indexed = ? WHERE id IN ({marks})", [int(indexed), *chunk])


def indexed_ids(conn: sqlite3.Connection) -> list[int]:
    return [r[0] for r in conn.execute("SELECT id FROM documents WHERE indexed = 1 ORDER BY id")]


def count_documents(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]


def category_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {r[0]: r[1] for r in conn.execute("SELECT category, COUNT(*) FROM documents GROUP BY category ORDER BY category")}


def set_metadata(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO index_metadata (key, value, updated_at) VALUES (?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, value, utc_now()),
    )


def get_metadata(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM index_metadata WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None
