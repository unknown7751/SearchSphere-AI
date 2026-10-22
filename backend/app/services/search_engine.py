"""SearchEngine: owns the in-memory index and keeps it in sync with SQLite.

SQLite is the source of truth for documents. The index is derived data: it is rebuilt
from the database at start-up (``rebuild``) and updated incrementally on insert/delete.
A re-entrant lock serialises index mutation against concurrent request threads.
"""
from __future__ import annotations

import json
import sqlite3
import threading

from app.database import repository as repo
from app.models.document import Document
from app.services.advanced_retrieval import AdvancedRetriever
from app.services.boolean_retrieval import BooleanRetriever
from app.services.ingestion import ExtractedDocument
from app.services.inverted_index import InvertedIndex
from app.services.preprocessing import Preprocessor
from app.services.ranking import Ranker, TfidfModel
from app.services.tolerant_retrieval import TolerantRetriever


class DuplicateContentError(Exception):
    """An uploaded document has the same normalised text as an existing document."""

    def __init__(self, existing_id: int):
        super().__init__(f"Identical content already stored as document {existing_id}")
        self.existing_id = existing_id


class SourceUrlConflict(Exception):
    """A crawled URL is already stored as a document that was not created by the crawler."""

    def __init__(self, existing_id: int):
        super().__init__(f"URL already stored as non-crawled document {existing_id}")
        self.existing_id = existing_id


class SearchEngine:
    def __init__(self, preprocessor: Preprocessor | None = None, wildcard_limit: int = 50):
        self.preprocessor = preprocessor or Preprocessor()
        self.index = InvertedIndex()
        self.model = TfidfModel(self.index)
        self.ranker = Ranker(self.model)
        self.boolean = BooleanRetriever(self.index, self.preprocessor.index_terms)
        self.tolerant = TolerantRetriever(self.index, wildcard_limit)
        self.advanced = AdvancedRetriever(self.model, self.ranker, self.preprocessor, self.boolean)
        self.lock = threading.RLock()

    # ------------------------------------------------------------------ indexing
    def _index_document(self, doc_id: int, text: str) -> None:
        analysis = self.preprocessor.analyze(text)
        self.index.add_document(doc_id, analysis.index_terms, analysis.surface_terms)

    def rebuild(self, conn: sqlite3.Connection) -> dict:
        """Rebuild the whole index from the documents table and mark every document indexed."""
        with self.lock:
            self.index.clear()
            try:
                for doc in repo.iter_all_documents(conn):
                    self._index_document(doc.id, f"{doc.title}. {doc.text}")
                repo.set_indexed(conn, None, True)
                repo.set_metadata(conn, "last_rebuild", repo.utc_now())
                conn.commit()
            except Exception:
                conn.rollback()
                self.index.clear()
                raise
            return self.index.stats()

    def add_document(self, conn: sqlite3.Connection, **fields) -> Document:
        """Insert a document row and index it atomically (DB transaction + index update)."""
        with self.lock:
            doc_id = None
            try:
                doc_id = repo.insert_document(conn, **fields)
                self._index_document(doc_id, f"{fields['title']}. {fields['text']}")
                repo.set_indexed(conn, [doc_id], True)
                conn.commit()
            except Exception:
                conn.rollback()
                if doc_id is not None:
                    self.index.remove_document(doc_id)
                raise
            return repo.get_document(conn, doc_id)

    def ingest(self, conn: sqlite3.Connection, extracted: ExtractedDocument, category: str) -> tuple[Document, int]:
        """Store an extracted upload and make it searchable immediately.

        Same atomic path as :meth:`add_document` (insert row -> preprocess -> update the
        inverted index / TF / DF -> flag indexed), so no restart or rebuild is needed.
        Returns the stored document and its token count (index terms after preprocessing).
        """
        with self.lock:
            existing = repo.find_by_content_hash(conn, extracted.content_hash)
            if existing is not None:
                raise DuplicateContentError(existing.id)
            doc = self.add_document(
                conn,
                title=extracted.title,
                text=extracted.text,
                category=category,
                source_type="user",
                file_type=extracted.file_type,
                source_name=extracted.source_name,
                content_hash=extracted.content_hash,
                metadata_json=json.dumps(extracted.metadata, sort_keys=True) if extracted.metadata else None,
            )
            return doc, self.index.doc_length(doc.id)

    def store_crawled(
        self,
        conn: sqlite3.Connection,
        *,
        url: str,
        title: str,
        text: str,
        category: str,
        content_hash: str,
        metadata: dict,
    ) -> tuple[Document, str]:
        """Store (or refresh) a crawled page and keep the index consistent.  The page URL is its identity.

        Returns ``(document, outcome)`` where outcome is ``created`` (new row, indexed), ``updated``
        (same URL, content changed: row rewritten and re-indexed) or ``unchanged`` (same URL and
        content: only the crawl metadata is refreshed, nothing is re-indexed).  Raises
        :class:`DuplicateContentError` when a *different* document already has identical text and
        :class:`SourceUrlConflict` when the URL belongs to a user/seed document.
        """
        metadata_json = json.dumps(metadata, sort_keys=True)
        with self.lock:
            existing = repo.find_by_source_url(conn, url)
            if existing is None:
                twin = repo.find_by_content_hash(conn, content_hash)
                if twin is not None:
                    raise DuplicateContentError(twin.id)
                doc = self.add_document(
                    conn, title=title, text=text, category=category, source_type="crawled", source_url=url,
                    file_type="html", source_name=metadata.get("host"), content_hash=content_hash,
                    metadata_json=metadata_json,
                )
                return doc, "created"
            if existing.source_type != "crawled":
                raise SourceUrlConflict(existing.id)
            if existing.content_hash == content_hash:
                repo.update_document_metadata(conn, existing.id, metadata_json)
                conn.commit()
                return repo.get_document(conn, existing.id), "unchanged"
            twin = repo.find_by_content_hash(conn, content_hash)
            if twin is not None and twin.id != existing.id:
                raise DuplicateContentError(twin.id)
            try:
                repo.update_document_content(
                    conn, existing.id, title=title, text=text, content_hash=content_hash, metadata_json=metadata_json
                )
                self.index.remove_document(existing.id)
                self._index_document(existing.id, f"{title}. {text}")
                conn.commit()
            except Exception:
                conn.rollback()
                self.index.remove_document(existing.id)  # restore the previous index entry from the old text
                self._index_document(existing.id, f"{existing.title}. {existing.text}")
                raise
            return repo.get_document(conn, existing.id), "updated"

    def delete_document(self, conn: sqlite3.Connection, doc_id: int) -> bool:
        with self.lock:
            try:
                deleted = repo.delete_document(conn, doc_id)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            if deleted:
                self.index.remove_document(doc_id)
            return deleted

    def check(self, conn: sqlite3.Connection) -> dict:
        """Structural index checks plus agreement with the database's indexed documents."""
        with self.lock:
            problems = self.index.check_consistency()
            db_ids = set(repo.indexed_ids(conn))
            idx_ids = set(self.index.all_doc_ids())
            if db_ids - idx_ids:
                problems.append(f"indexed in DB but missing from index: {sorted(db_ids - idx_ids)[:10]}")
            if idx_ids - db_ids:
                problems.append(f"in index but not flagged indexed in DB: {sorted(idx_ids - db_ids)[:10]}")
            return {"consistent": not problems, "problems": problems, "stats": self.index.stats()}
