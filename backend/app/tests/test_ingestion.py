"""Document ingestion: extraction service, schema migration and the upload API."""
import sqlite3

import pytest

from app.database import repository as repo
from app.database.connection import connect
from app.database.schema import init_db
from app.services import ingestion as ing

LIMITS = dict(max_bytes=1_000_000, max_chars=200_000)


def extract(name, data, **kw):
    return ing.extract_document(name, data, **{**LIMITS, **kw})


def make_pdf(pages: list[str], title: str | None = None) -> bytes:
    fitz = pytest.importorskip("pymupdf")
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    if title:
        doc.set_metadata({"title": title, "author": "Test Author"})
    data = doc.tobytes()
    doc.close()
    return data


# ------------------------------------------------------------------ extraction service
def test_txt_extraction_and_title_from_first_line():
    doc = extract("notes.txt", b"Quokka Habitats\r\n\r\n\r\n\r\nQuokkas live on islands.   \r\n")
    assert doc.file_type == "txt" and doc.source_name == "notes.txt"
    assert doc.title == "Quokka Habitats"
    assert doc.text == "Quokka Habitats\n\nQuokkas live on islands."
    assert len(doc.content_hash) == 64


def test_title_falls_back_to_file_name_for_long_first_line():
    doc = extract("my_cool-file.txt", ("word " * 100).encode())
    assert doc.title == "my cool file"


def test_explicit_title_wins():
    assert extract("a.txt", b"hello world", title="  Custom  ").title == "Custom"


@pytest.mark.parametrize("raw", ["café naïve".encode("utf-8"), "café naïve".encode("cp1252"), "café naïve".encode("utf-16"),
                                 b"\xef\xbb\xbfcaf\xc3\xa9 na\xc3\xafve"])
def test_decoding_is_safe_for_common_encodings(raw):
    assert extract("e.txt", raw).text == "café naïve"


def test_binary_data_in_txt_is_rejected():
    with pytest.raises(ing.IngestionError) as exc:
        extract("x.txt", b"abc\x00\x01\x02def")
    assert exc.value.code == "invalid_text_file"


@pytest.mark.parametrize("name", ["a.docx", "a.exe", "noextension", "a.txt.exe", ""])
def test_unsupported_extension(name):
    with pytest.raises(ing.IngestionError) as exc:
        extract(name, b"hello")
    assert exc.value.status_code == 400 and exc.value.code == "unsupported_file_type"


def test_extension_is_case_insensitive_and_path_is_stripped():
    assert extract("C:\\temp\\NOTES.TXT", b"hello there").source_name == "NOTES.TXT"


def test_empty_file_and_whitespace_only_file():
    with pytest.raises(ing.IngestionError) as exc:
        extract("a.txt", b"")
    assert exc.value.code == "empty_file"
    with pytest.raises(ing.IngestionError) as exc:
        extract("a.txt", b" \n\t \r\n ")
    assert exc.value.code == "empty_document"


def test_size_limits():
    with pytest.raises(ing.IngestionError) as exc:
        extract("a.txt", b"x" * 11, max_bytes=10)
    assert exc.value.status_code == 413 and exc.value.code == "file_too_large"
    with pytest.raises(ing.IngestionError) as exc:
        extract("a.txt", b"word " * 100, max_chars=50)
    assert exc.value.code == "document_too_long"


def test_content_hash_ignores_case_and_whitespace():
    assert ing.content_hash("Hello   World\n") == ing.content_hash("hello world")
    assert ing.content_hash("hello world") != ing.content_hash("hello there")


def test_pdf_extraction_page_by_page_with_metadata():
    pdf = make_pdf(["Alpha zyzzyva page one", "Beta page two"], title="Zyzzyva Study")
    doc = extract("paper.pdf", pdf)
    assert doc.file_type == "pdf" and doc.title == "Zyzzyva Study"
    assert "Alpha zyzzyva page one" in doc.text and "Beta page two" in doc.text
    assert doc.text.index("page one") < doc.text.index("page two")
    assert doc.metadata["page_count"] == 2 and doc.metadata["pages_with_text"] == 2
    assert doc.metadata["author"] == "Test Author"


def test_pdf_without_metadata_title_uses_first_line():
    assert extract("p.pdf", make_pdf(["Heading line here"])).title == "Heading line here"


def test_malformed_pdf():
    pytest.importorskip("pymupdf")
    with pytest.raises(ing.IngestionError) as exc:
        extract("bad.pdf", b"%PDF-1.4 this is definitely not a real pdf")
    assert exc.value.status_code == 400 and exc.value.code in {"malformed_pdf", "empty_document", "pdf_extraction_failed"}
    with pytest.raises(ing.IngestionError):
        extract("bad.pdf", b"just some random text")


def test_pdf_with_no_text_layer():
    fitz = pytest.importorskip("pymupdf")
    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    with pytest.raises(ing.IngestionError) as exc:
        extract("blank.pdf", data)
    assert exc.value.code == "empty_document" and "OCR" in exc.value.message


def test_missing_pymupdf_fails_gracefully(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name in ("fitz", "pymupdf"):
            raise ImportError("no fitz")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert ing.pdf_supported() is False
    with pytest.raises(ing.IngestionError) as exc:
        extract("a.pdf", b"%PDF-1.4")
    assert exc.value.status_code == 501 and exc.value.code == "pdf_support_unavailable"


# ------------------------------------------------------------------ schema migration
def test_old_phase1_database_is_migrated(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(
        """CREATE TABLE documents (id INTEGER PRIMARY KEY AUTOINCREMENT, external_id TEXT UNIQUE, title TEXT NOT NULL,
        text TEXT NOT NULL, category TEXT NOT NULL, source_type TEXT NOT NULL, source_url TEXT, published_at TEXT,
        ingested_at TEXT NOT NULL, word_count INTEGER NOT NULL, indexed INTEGER NOT NULL DEFAULT 0);
        INSERT INTO documents (title, text, category, source_type, ingested_at, word_count)
        VALUES ('Old', 'old text body', 'c', 'user', '2024-01-01T00:00:00+00:00', 3);"""
    )
    old.commit()
    old.close()
    conn = connect(path)
    init_db(conn)
    init_db(conn)  # idempotent
    columns = {r[1] for r in conn.execute("PRAGMA table_info(documents)")}
    assert {"file_type", "source_name", "updated_at", "content_hash", "metadata_json"} <= columns
    doc = repo.get_document(conn, 1)
    assert doc.title == "Old" and doc.file_type is None
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"evaluation_queries", "relevance_judgments"} <= tables
    conn.close()


# ------------------------------------------------------------------ upload API
def upload(client, name, data, **form):
    return client.post("/api/documents/upload", files={"file": (name, data)}, data=form)


def search_ids(client, query):
    return [r["doc_id"] for r in client.post("/api/search", json={"query": query}).json()["results"]]


def test_txt_upload_becomes_searchable_immediately(client):
    assert search_ids(client, "zyzzyva") == []
    r = upload(client, "quokka.txt", b"Zyzzyva Notes\n\nThe zyzzyva beetle lives in tropical forests.", category="Biology")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["file_type"] == "txt" and body["title"] == "Zyzzyva Notes" and body["category"] == "Biology"
    assert body["indexed"] is True and body["token_count"] > 0 and body["word_count"] == 9
    assert r.headers["location"] == f"/api/documents/{body['document_id']}"
    assert search_ids(client, "zyzzyva") == [body["document_id"]]


def test_upload_pipeline_consistency(client):
    doc_id = upload(client, "n.txt", b"Axolotl regeneration\nAxolotl limbs regrow quickly.").json()["document_id"]
    # database row with metadata
    detail = client.get(f"/api/documents/{doc_id}").json()
    assert detail["file_type"] == "txt" and detail["source_name"] == "n.txt" and detail["source_type"] == "user"
    assert detail["updated_at"] and detail["indexed"] is True
    # inverted index has the term with the right tf and df, TF-IDF can use it
    posting = client.get("/api/workbench/inverted-index", params={"term": "axolotl"}).json()
    assert posting["document_frequency"] == 1 and posting["postings"][0]["doc_id"] == doc_id
    assert posting["postings"][0]["tf"] == 3  # 'axolotl' in title+text
    tfidf = client.post("/api/workbench/tfidf", json={"document_ids": [doc_id], "query": "axolotl"}).json()
    assert tfidf["documents"][0]["query_term_weights"][0]["tfidf"] > 0
    # whole index remains consistent
    check = client.get("/api/index/check").json()
    assert check["consistent"], check["problems"]
    assert client.get("/api/health").json()["indexed_documents"] == 6


def test_deleting_an_uploaded_document_removes_it_from_retrieval(client):
    doc_id = upload(client, "d.txt", b"Platypus electroreception is remarkable.").json()["document_id"]
    assert search_ids(client, "platypus") == [doc_id]
    assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    assert search_ids(client, "platypus") == []
    assert client.post("/api/search/boolean", json={"query": "platypus"}).json()["matching_doc_ids"] == []
    assert client.get("/api/workbench/inverted-index", params={"term": "platypus"}).json()["document_frequency"] == 0
    assert client.get("/api/index/check").json()["consistent"]
    # the same text can be uploaded again after deletion
    assert upload(client, "d.txt", b"Platypus electroreception is remarkable.").status_code == 201


def test_pdf_upload_searchable_with_metadata(client):
    pdf = make_pdf(["Quasar luminosity measurements", "Second page about pulsars"], title="Quasar Paper")
    r = upload(client, "quasar.pdf", pdf, category="Astronomy")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["file_type"] == "pdf" and body["title"] == "Quasar Paper"
    assert body["metadata"]["page_count"] == 2
    assert search_ids(client, "pulsars") == [body["document_id"]]  # text of page 2 is indexed
    assert client.get(f"/api/documents/{body['document_id']}").json()["metadata"]["author"] == "Test Author"


def test_upload_validation_errors(client):
    r = upload(client, "a.docx", b"hello")
    assert r.status_code == 400 and r.json()["error"]["code"] == "unsupported_file_type"
    r = upload(client, "a.txt", b"")
    assert r.status_code == 400 and r.json()["error"]["code"] == "empty_file"
    r = upload(client, "a.txt", b"   \n  ")
    assert r.status_code == 400 and r.json()["error"]["code"] == "empty_document"
    r = upload(client, "a.pdf", b"not a pdf at all")
    assert r.status_code == 400
    r = client.post("/api/documents/upload")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = upload(client, "a.txt", b"hello world", category="   ")
    assert r.status_code == 422
    assert client.get("/api/health").json()["documents"] == 5  # nothing was stored


def test_upload_too_large(client):
    limit = client.app.state.settings.max_upload_bytes
    r = upload(client, "big.txt", b"a" * (limit + 1))
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"


def test_duplicate_upload_is_rejected_with_409(client):
    first = upload(client, "one.txt", b"Narwhal tusks are sensory organs.").json()["document_id"]
    r = upload(client, "two.txt", b"narwhal   TUSKS are sensory organs.\n")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "duplicate_document"
    assert r.json()["error"]["details"]["existing_document_id"] == first


def test_upload_errors_do_not_leak_internals(client):
    r = upload(client, "a.pdf", b"%PDF-1.4 garbage")
    assert "Traceback" not in r.text and "fitz" not in r.text and "C:\\" not in r.text
