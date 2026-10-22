"""Turn an uploaded TXT / PDF file into clean text plus metadata.

This module only *extracts and validates*; storing the document and updating the inverted
index is done by :meth:`SearchEngine.ingest` so that the same indexing code path is used
for seeded, JSON-created and uploaded documents.

Pipeline: validate extension -> validate size -> extract text (page by page for PDF) ->
normalise text -> validate non-empty / length -> derive title -> content hash.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import PurePath

SUPPORTED_EXTENSIONS = {".txt": "txt", ".pdf": "pdf"}
TITLE_MAX_CHARS = 120

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BLANK_LINES = re.compile(r"\n{3,}")
_SPACES = re.compile(r"[ \t]+")


class IngestionError(Exception):
    """A user-facing ingestion failure with an HTTP status and stable error code."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass
class ExtractedDocument:
    title: str
    text: str
    file_type: str
    source_name: str
    content_hash: str
    metadata: dict = field(default_factory=dict)


def _load_pymupdf():
    """Import PyMuPDF (module ``pymupdf``; older releases only provide the ``fitz`` alias)."""
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        import fitz
        return fitz


def pdf_supported() -> bool:
    try:
        _load_pymupdf()
    except ImportError:
        return False
    return True


def file_type_for(filename: str) -> str:
    """Validate the extension and return the file type ('txt' or 'pdf')."""
    name = PurePath((filename or "").replace("\\", "/")).name
    suffix = PurePath(name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise IngestionError(
            400, "unsupported_file_type", f"Unsupported file type {suffix or '(none)'!r}. Upload a .txt or .pdf file."
        )
    return SUPPORTED_EXTENSIONS[suffix]


def decode_text(data: bytes) -> str:
    """Decode bytes safely: BOM-aware UTF-8/UTF-16, then UTF-8, then Windows-1252."""
    if b"\x00" in data and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise IngestionError(400, "invalid_text_file", "The file contains binary data and is not a plain-text file.")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise IngestionError(400, "invalid_text_file", "The file is not valid UTF-16 text.") from exc
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def normalize_text(text: str) -> str:
    """Unicode NFC, unix newlines, no control characters, tidy whitespace and blank lines."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def content_hash(text: str) -> str:
    """SHA-256 of the lower-cased, whitespace-collapsed text (duplicate detection)."""
    canonical = " ".join(text.lower().split())
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def derive_title(text: str, source_name: str, preferred: str | None = None) -> str:
    """Explicit title > first short line of the text > file name without extension."""
    if preferred and preferred.strip():
        return preferred.strip()[:300]
    for line in text.split("\n"):
        line = line.strip()
        if line:
            if len(line) <= TITLE_MAX_CHARS:
                return line
            break
    stem = PurePath(source_name.replace("\\", "/")).stem
    title = re.sub(r"[_\-]+", " ", stem).strip()
    return title or "Untitled document"


def _extract_pdf(data: bytes) -> tuple[str, dict]:
    try:
        fitz = _load_pymupdf()
    except ImportError as exc:
        raise IngestionError(
            501, "pdf_support_unavailable", "PDF support is not available: install PyMuPDF (pip install pymupdf)."
        ) from exc
    try:
        pdf = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises several unrelated exception types for corrupt input
        raise IngestionError(400, "malformed_pdf", "The file is not a readable PDF document.") from exc
    try:
        if pdf.needs_pass or pdf.is_encrypted:
            raise IngestionError(400, "encrypted_pdf", "Password-protected PDFs cannot be indexed.")
        try:
            pages = [page.get_text() for page in pdf]  # page by page, in reading order
        except Exception as exc:
            raise IngestionError(400, "pdf_extraction_failed", "Text could not be extracted from the PDF.") from exc
        info = pdf.metadata or {}
        metadata = {
            "page_count": pdf.page_count,
            "pages_with_text": sum(1 for p in pages if p.strip()),
            **{k: info[k].strip() for k in ("title", "author", "subject") if info.get(k) and info[k].strip()},
        }
        return "\n\n".join(pages), metadata
    finally:
        pdf.close()


def extract_document(
    filename: str,
    data: bytes,
    *,
    max_bytes: int,
    max_chars: int,
    title: str | None = None,
) -> ExtractedDocument:
    """Validate and extract an uploaded file. Raises :class:`IngestionError` on any problem."""
    file_type = file_type_for(filename)
    if not data:
        raise IngestionError(400, "empty_file", "The uploaded file is empty.")
    if len(data) > max_bytes:
        raise IngestionError(413, "file_too_large", f"The file exceeds the upload limit of {max_bytes} bytes.")

    metadata: dict = {}
    if file_type == "pdf":
        raw, metadata = _extract_pdf(data)
    else:
        raw = decode_text(data)
    text = normalize_text(raw)
    if not text:
        hint = " (scanned PDFs need OCR, which is not supported)" if file_type == "pdf" else ""
        raise IngestionError(400, "empty_document", f"No text could be extracted from the file{hint}.")
    if len(text) > max_chars:
        raise IngestionError(413, "document_too_long", f"The extracted text has {len(text)} characters; the limit is {max_chars}.")

    source_name = PurePath(filename.replace("\\", "/")).name
    preferred = title or metadata.get("title")
    return ExtractedDocument(
        title=derive_title(text, source_name, preferred),
        text=text,
        file_type=file_type,
        source_name=source_name,
        content_hash=content_hash(text),
        metadata=metadata,
    )
