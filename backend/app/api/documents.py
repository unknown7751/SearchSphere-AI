import math
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import get_conn, get_engine, make_snippet
from app.core.errors import AppError
from app.database import repository as repo
from app.models.document import Document
from app.schemas.documents import DocumentCreate, DocumentDetail, DocumentPage, DocumentSummary
from app.services.search_engine import SearchEngine

router = APIRouter(prefix="/documents", tags=["documents"])


def to_summary(doc: Document) -> dict:
    return {
        "id": doc.id,
        "external_id": doc.external_id,
        "title": doc.title,
        "category": doc.category,
        "source_type": doc.source_type,
        "source_url": doc.source_url,
        "published_at": doc.published_at,
        "ingested_at": doc.ingested_at,
        "word_count": doc.word_count,
        "indexed": doc.indexed,
        "snippet": make_snippet(doc.text),
    }


@router.get("", response_model=DocumentPage)
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str | None = Query(None, max_length=100),
    source_type: Literal["seed", "user", "crawled"] | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
):
    docs, total = repo.list_documents(conn, page=page, page_size=page_size, category=category, source_type=source_type)
    return {
        "items": [to_summary(d) for d in docs],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


@router.post("", response_model=DocumentDetail, status_code=201)
def create_document(
    body: DocumentCreate,
    response: Response,
    engine: SearchEngine = Depends(get_engine),
    conn: sqlite3.Connection = Depends(get_conn),
):
    try:
        doc = engine.add_document(
            conn,
            title=body.title,
            text=body.text,
            category=body.category,
            source_type="user",
            source_url=body.source_url,
            published_at=body.published_at.isoformat() if body.published_at else None,
        )
    except sqlite3.IntegrityError as exc:
        raise AppError(409, "duplicate_document", "A document with this source URL already exists.") from exc
    response.headers["Location"] = f"/api/documents/{doc.id}"
    return {**to_summary(doc), "text": doc.text}


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(document_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    doc = repo.get_document(conn, document_id)
    if doc is None:
        raise AppError(404, "document_not_found", f"Document {document_id} does not exist.")
    return {**to_summary(doc), "text": doc.text}


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: int,
    engine: SearchEngine = Depends(get_engine),
    conn: sqlite3.Connection = Depends(get_conn),
):
    if not engine.delete_document(conn, document_id):
        raise AppError(404, "document_not_found", f"Document {document_id} does not exist.")
    return Response(status_code=204)
