import json
import math
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile

from app.api.deps import get_conn, get_engine, make_snippet
from app.core.errors import AppError
from app.database import repository as repo
from app.models.document import Document
from app.schemas.advanced import UploadResponse
from app.schemas.documents import DocumentCreate, DocumentDetail, DocumentPage, DocumentSummary
from app.services.ingestion import IngestionError, extract_document
from app.services.search_engine import DuplicateContentError, SearchEngine

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
        "file_type": doc.file_type,
        "source_name": doc.source_name,
        "updated_at": doc.updated_at,
        "metadata": json.loads(doc.metadata_json) if doc.metadata_json else None,
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


@router.post("/upload", response_model=UploadResponse, status_code=201)
def upload_document(
    request: Request,
    response: Response,
    file: UploadFile = File(..., description="A .txt or .pdf file"),
    title: str | None = Form(default=None, max_length=300),
    category: str = Form(default="Uploaded", min_length=1, max_length=100),
    engine: SearchEngine = Depends(get_engine),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Ingest an uploaded file: validate -> extract -> normalise -> store -> preprocess -> index.

    The document is searchable as soon as this call returns; no restart or rebuild is needed.
    """
    limits = request.app.state.settings
    data = file.file.read(limits.max_upload_bytes + 1)  # never read more than the limit allows
    try:
        extracted = extract_document(
            file.filename or "",
            data,
            max_bytes=limits.max_upload_bytes,
            max_chars=limits.max_document_chars,
            title=title,
        )
        category = category.strip()
        if not category:
            raise IngestionError(422, "validation_error", "category must not be blank")
        doc, token_count = engine.ingest(conn, extracted, category)
    except IngestionError as exc:
        raise AppError(exc.status_code, exc.code, exc.message) from exc
    except DuplicateContentError as exc:
        raise AppError(
            409, "duplicate_document", f"This content is already stored as document {exc.existing_id}.",
            {"existing_document_id": exc.existing_id},
        ) from exc
    location = f"/api/documents/{doc.id}"
    response.headers["Location"] = location
    return {
        "document_id": doc.id,
        "title": doc.title,
        "file_type": extracted.file_type,
        "category": doc.category,
        "source_name": extracted.source_name,
        "word_count": doc.word_count,
        "token_count": token_count,
        "indexed": doc.indexed,
        "created_at": doc.ingested_at,
        "metadata": extracted.metadata,
        "location": location,
    }


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
