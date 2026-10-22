"""Idempotent loader for the sample/demo corpus in ``data/seed_documents.json``."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.core.config import DATA_DIR
from app.database import repository as repo

SEED_PATH = DATA_DIR / "seed_documents.json"


def load_seed_file(path: Path = SEED_PATH) -> list[dict]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    docs = payload["documents"]
    ids = [d["id"] for d in docs]
    if len(ids) != len(set(ids)):
        raise ValueError("Seed file contains duplicate document IDs")
    for d in docs:
        for key in ("id", "title", "text", "category"):
            if not str(d.get(key, "")).strip():
                raise ValueError(f"Seed document {d.get('id')!r} is missing {key!r}")
    return docs


def seed_database(conn: sqlite3.Connection, path: Path = SEED_PATH) -> dict[str, int]:
    """Insert or update seed documents keyed by their stable ``external_id``.

    Running this repeatedly never creates duplicates. Changed seed text updates the
    existing row and clears its ``indexed`` flag; callers should then rebuild the index.
    """
    docs = load_seed_file(path)
    inserted = updated = unchanged = 0
    try:
        for d in docs:
            row = conn.execute(
                "SELECT id, title, text, category FROM documents WHERE external_id = ?", (d["id"],)
            ).fetchone()
            if row is None:
                repo.insert_document(
                    conn,
                    title=d["title"],
                    text=d["text"],
                    category=d["category"],
                    source_type="seed",
                    published_at=d.get("published_at"),
                    external_id=d["id"],
                )
                inserted += 1
            elif (row["title"], row["text"], row["category"]) != (d["title"], d["text"], d["category"]):
                conn.execute(
                    "UPDATE documents SET title = ?, text = ?, category = ?, word_count = ?, indexed = 0 WHERE id = ?",
                    (d["title"], d["text"], d["category"], repo.count_words(d["text"]), row["id"]),
                )
                updated += 1
            else:
                unchanged += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"inserted": inserted, "updated": updated, "unchanged": unchanged, "total": len(docs)}
