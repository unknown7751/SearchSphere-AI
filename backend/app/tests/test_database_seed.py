import sqlite3

import pytest

from app.database import repository as repo
from app.database.connection import connect
from app.database.schema import init_db
from app.database.seed import load_seed_file, seed_database
from app.services.search_engine import SearchEngine


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "t.db")
    init_db(c)
    yield c
    c.close()


def test_init_db_is_idempotent(conn):
    init_db(conn)
    init_db(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"documents", "index_metadata"} <= tables
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert {"ux_documents_source_url", "ix_documents_category", "ix_documents_source_type"} <= indexes


def test_constraints(conn):
    ok = dict(title="t", text="x y", category="c", source_type="user")
    repo.insert_document(conn, **ok, external_id="e1", source_url="https://a")
    with pytest.raises(sqlite3.IntegrityError):  # duplicate external_id
        repo.insert_document(conn, **ok, external_id="e1")
    with pytest.raises(sqlite3.IntegrityError):  # duplicate source_url
        repo.insert_document(conn, **ok, source_url="https://a")
    with pytest.raises(sqlite3.IntegrityError):  # invalid source type
        repo.insert_document(conn, **{**ok, "source_type": "alien"})
    with pytest.raises(sqlite3.IntegrityError):  # blank text
        repo.insert_document(conn, **{**ok, "text": "  "})
    repo.insert_document(conn, **ok)  # NULL source_url / external_id may repeat
    repo.insert_document(conn, **ok)
    conn.rollback()


def test_word_count_and_defaults(conn):
    doc_id = repo.insert_document(conn, title="t", text="one two  three, four!", category="c", source_type="user")
    conn.commit()
    doc = repo.get_document(conn, doc_id)
    assert doc.word_count == 4 and doc.indexed is False and doc.ingested_at.endswith("+00:00")


def test_parameterised_sql_resists_injection(conn):
    repo.insert_document(conn, title="t", text="x", category="c", source_type="user")
    conn.commit()
    docs, total = repo.list_documents(conn, category="'; DROP TABLE documents; --")
    assert total == 0 and docs == []
    assert repo.count_documents(conn) == 1


def test_data_persists_across_connections(tmp_path):
    path = tmp_path / "p.db"
    c1 = connect(path)
    init_db(c1)
    repo.insert_document(c1, title="t", text="persist me", category="c", source_type="user")
    c1.commit()
    c1.close()
    c2 = connect(path)
    assert repo.count_documents(c2) == 1
    c2.close()


# ------------------------------------------------------------------ seed corpus
def test_seed_file_quality():
    docs = load_seed_file()
    assert len(docs) >= 100
    assert len({d["id"] for d in docs}) == len(docs)
    assert len({d["title"] for d in docs}) == len(docs)
    assert len({d["text"] for d in docs}) == len(docs)
    categories = {d["category"] for d in docs}
    assert len(categories) >= 8
    for d in docs:
        assert len(d["title"].split()) >= 2 and len(d["text"].split()) >= 20, d["id"]


def test_seed_is_idempotent(conn):
    first = seed_database(conn)
    assert first["inserted"] == first["total"] >= 100 and first["updated"] == 0
    second = seed_database(conn)
    assert second == {"inserted": 0, "updated": 0, "unchanged": first["total"], "total": first["total"]}
    assert repo.count_documents(conn) == first["total"]
    assert repo.list_documents(conn, source_type="seed", page_size=1)[1] == first["total"]


def test_seed_updates_changed_documents(conn, tmp_path):
    import json
    from app.core.config import DATA_DIR
    payload = json.loads((DATA_DIR / "seed_documents.json").read_text(encoding="utf-8"))
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    seed_database(conn, path)
    payload["documents"][0]["text"] = "completely different replacement text for the first document here"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = seed_database(conn, path)
    assert result["updated"] == 1 and result["inserted"] == 0
    row = conn.execute("SELECT text, indexed FROM documents WHERE external_id = 'seed-001'").fetchone()
    assert row["text"].startswith("completely different") and row["indexed"] == 0


def test_seed_corpus_supports_the_required_demonstrations(conn):
    seed_database(conn)
    engine = SearchEngine()
    stats = engine.rebuild(conn)
    assert stats["num_documents"] >= 100 and stats["vocabulary_size"] > 500
    assert engine.check(conn)["consistent"] is True
    ids = lambda q: engine.boolean.search(q).doc_ids  # noqa: E731
    assert len(ids("machine AND learning")) >= 2
    assert len(ids("python OR java")) > len(ids("python"))
    assert 0 < len(ids("machine AND NOT hardware")) < len(ids("machine"))
    assert len(ids("(python OR java) AND programming")) >= 2
    for pattern in ("mach*", "pro*", "secur*", "comput*r", "p*thon", "algor*hm"):
        assert engine.tolerant.search(pattern).total_matches >= 1, pattern
    assert [m.term for m in engine.tolerant.search("p*thon").matched_terms] == ["python"]
    top = engine.ranker.rank(engine.preprocessor.index_terms("machine learning")).ranked
    assert len(top) >= 5 and top[0].score > top[-1].score


def test_rebuild_marks_documents_indexed_and_is_repeatable(conn):
    seed_database(conn)
    engine = SearchEngine()
    s1 = engine.rebuild(conn)
    s2 = engine.rebuild(conn)
    assert s1 == s2
    assert len(repo.indexed_ids(conn)) == repo.count_documents(conn)
    assert repo.get_metadata(conn, "last_rebuild")


def test_engine_add_and_delete_keep_db_and_index_in_sync(conn):
    seed_database(conn)
    engine = SearchEngine()
    engine.rebuild(conn)
    n = engine.index.num_docs
    doc = engine.add_document(conn, title="Zebra Facts", text="zebras have stripes", category="x", source_type="user")
    assert doc.indexed and engine.index.num_docs == n + 1
    assert engine.boolean.search("zebra").doc_ids == [doc.id]
    assert engine.check(conn)["consistent"]
    assert engine.delete_document(conn, doc.id) is True
    assert engine.boolean.search("zebra").doc_ids == []
    assert engine.index.num_docs == n and engine.check(conn)["consistent"]
    assert engine.delete_document(conn, doc.id) is False


def test_failed_insert_rolls_back_database_and_index(conn):
    engine = SearchEngine()
    engine.add_document(conn, title="a", text="alpha", category="c", source_type="user", source_url="https://x")
    with pytest.raises(sqlite3.IntegrityError):
        engine.add_document(conn, title="b", text="beta", category="c", source_type="user", source_url="https://x")
    assert repo.count_documents(conn) == 1 and engine.index.num_docs == 1
    assert engine.check(conn)["consistent"]
