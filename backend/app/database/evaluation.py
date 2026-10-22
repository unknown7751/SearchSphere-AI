"""Evaluation dataset persistence: queries and binary relevance judgments.

The dataset is defined in ``data/evaluation_queries.json`` by documents' stable
``external_id`` and loaded idempotently into ``evaluation_queries`` / ``relevance_judgments``
(resolved to the current database IDs), so it is reproducible after any rebuild.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.core.config import DATA_DIR

EVALUATION_PATH = DATA_DIR / "evaluation_queries.json"


@dataclass
class EvaluationQuery:
    id: int
    query: str
    description: str | None
    relevant_doc_ids: list[int]


def load_evaluation_file(path: Path = EVALUATION_PATH) -> list[dict]:
    queries = json.loads(Path(path).read_text(encoding="utf-8"))["queries"]
    seen = set()
    for q in queries:
        text = str(q.get("query", "")).strip()
        if not text or not q.get("relevant"):
            raise ValueError(f"Evaluation query {q.get('query')!r} needs text and at least one relevant document")
        if text in seen:
            raise ValueError(f"Duplicate evaluation query {text!r}")
        seen.add(text)
    return queries


def seed_evaluation(conn: sqlite3.Connection, path: Path = EVALUATION_PATH) -> dict[str, int]:
    """Replace the judgments of every dataset query with the file's contents (idempotent).

    Judged documents that do not exist in the database are skipped and counted.
    """
    queries = load_evaluation_file(path)
    judgments = missing = 0
    try:
        for q in queries:
            text = q["query"].strip()
            conn.execute(
                "INSERT INTO evaluation_queries (query_text, description) VALUES (?, ?)"
                " ON CONFLICT(query_text) DO UPDATE SET description = excluded.description",
                (text, q.get("description")),
            )
            query_id = conn.execute("SELECT id FROM evaluation_queries WHERE query_text = ?", (text,)).fetchone()[0]
            conn.execute("DELETE FROM relevance_judgments WHERE query_id = ?", (query_id,))
            for external_id in dict.fromkeys(q["relevant"]):
                row = conn.execute("SELECT id FROM documents WHERE external_id = ?", (external_id,)).fetchone()
                if row is None:
                    missing += 1
                    continue
                conn.execute(
                    "INSERT INTO relevance_judgments (query_id, document_id, relevance) VALUES (?, ?, 1)", (query_id, row[0])
                )
                judgments += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"queries": len(queries), "judgments": judgments, "missing_documents": missing}


def list_queries(conn: sqlite3.Connection) -> list[EvaluationQuery]:
    """All dataset queries that have at least one relevant document, with their judgments."""
    rows = conn.execute(
        "SELECT q.id, q.query_text, q.description, j.document_id FROM evaluation_queries q"
        " JOIN relevance_judgments j ON j.query_id = q.id AND j.relevance = 1 ORDER BY q.id, j.document_id"
    ).fetchall()
    out: dict[int, EvaluationQuery] = {}
    for row in rows:
        entry = out.setdefault(row["id"], EvaluationQuery(row["id"], row["query_text"], row["description"], []))
        entry.relevant_doc_ids.append(row["document_id"])
    return list(out.values())


def get_relevant_for_query(conn: sqlite3.Connection, query: str) -> list[int] | None:
    """Judged relevant IDs for a dataset query (exact text match), or None if there are none."""
    row = conn.execute("SELECT id FROM evaluation_queries WHERE query_text = ?", (query.strip(),)).fetchone()
    if row is None:
        return None
    ids = [
        r[0]
        for r in conn.execute(
            "SELECT document_id FROM relevance_judgments WHERE query_id = ? AND relevance = 1 ORDER BY document_id",
            (row[0],),
        )
    ]
    return ids or None
