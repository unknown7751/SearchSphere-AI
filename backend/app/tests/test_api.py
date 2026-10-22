"""API tests over a fresh temporary SQLite database holding five known documents.

Corpus (see conftest.API_DOCS; title and text are both indexed):
  1 Python Programming   2 Java Programming   3 Machine Learning
  4 Computer Hardware    5 Network Security
"""
import math

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def post(client, url, **body):
    return client.post(url, json=body)


# ------------------------------------------------------------------ health / errors
def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["documents"] == 5 and body["indexed_documents"] == 5
    assert body["vocabulary_size"] > 10


def test_openapi_docs_available(client):
    spec = client.get("/openapi.json").json()
    for path in ("/api/health", "/api/documents", "/api/search", "/api/search/boolean", "/api/search/tolerant",
                 "/api/search/suggestions", "/api/workbench/preprocess", "/api/workbench/incidence-matrix",
                 "/api/workbench/inverted-index", "/api/workbench/tfidf", "/api/workbench/cosine"):
        assert path in spec["paths"], path


def test_error_shape_has_no_internals(client):
    r = client.get("/api/documents/9999")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "document_not_found"
    text = r.text
    assert "Traceback" not in text and ".py" not in text and "C:\\" not in text

    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_cors_headers(client):
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    r = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers


# ------------------------------------------------------------------ documents
def test_create_and_get_document(client):
    r = post(client, "/api/documents", title="  Quantum Computing ", text="Qubits enable quantum algorithms.",
             category="Research", source_url="https://example.com/q", published_at="2024-05-01")
    assert r.status_code == 201
    doc = r.json()
    assert doc["id"] == 6 and r.headers["location"] == "/api/documents/6"
    assert doc["title"] == "Quantum Computing"  # trimmed
    assert doc["source_type"] == "user" and doc["indexed"] is True
    assert doc["word_count"] == 4
    assert doc["published_at"] == "2024-05-01" and doc["ingested_at"]

    got = client.get("/api/documents/6").json()
    assert got == doc
    assert client.get("/api/health").json()["indexed_documents"] == 6


def test_new_document_is_immediately_searchable(client):
    post(client, "/api/documents", title="Quantum Computing", text="Qubits enable quantum algorithms.", category="Research")
    assert post(client, "/api/search/boolean", query="quantum").json()["matching_doc_ids"] == [6]
    assert post(client, "/api/search/tolerant", pattern="qu*").json()["total_documents"] == 1
    top = post(client, "/api/search", query="qubits").json()["results"]
    assert [x["doc_id"] for x in top] == [6]


def test_delete_document(client):
    assert post(client, "/api/search/boolean", query="hardware").json()["matching_doc_ids"] == [4]
    r = client.delete("/api/documents/4")
    assert r.status_code == 204 and r.content == b""
    assert client.get("/api/documents/4").status_code == 404
    assert client.delete("/api/documents/4").status_code == 404
    assert post(client, "/api/search/boolean", query="hardware").json()["matching_doc_ids"] == []
    assert post(client, "/api/search/boolean", query="NOT hardware").json()["matching_doc_ids"] == [1, 2, 3, 5]
    assert post(client, "/api/search/tolerant", pattern="hard*").json()["total_matches"] == 0
    health = client.get("/api/health").json()
    assert health["documents"] == 4 and health["indexed_documents"] == 4
    check = client.get("/api/index/check").json()
    assert check["consistent"] is True, check


def test_list_documents_pagination_and_filters(client):
    r = client.get("/api/documents", params={"page_size": 2}).json()
    assert r["total"] == 5 and r["total_pages"] == 3 and [d["id"] for d in r["items"]] == [1, 2]
    assert "text" not in r["items"][0] and r["items"][0]["snippet"]
    assert [d["id"] for d in client.get("/api/documents", params={"page_size": 2, "page": 3}).json()["items"]] == [5]
    assert client.get("/api/documents", params={"page": 9}).json()["items"] == []
    prog = client.get("/api/documents", params={"category": "Programming"}).json()
    assert prog["total"] == 2
    assert client.get("/api/documents", params={"source_type": "seed"}).json()["total"] == 0
    assert client.get("/api/documents", params={"source_type": "bogus"}).status_code == 422
    assert client.get("/api/documents", params={"page_size": 1000}).status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "", "text": "x", "category": "c"},
        {"title": "t", "text": "   ", "category": "c"},
        {"title": "t", "text": "x"},
        {"title": "t", "text": "x", "category": "c", "source_url": "ftp://x"},
        {"title": "t", "text": "x", "category": "c", "published_at": "not-a-date"},
        {"title": "t" * 301, "text": "x", "category": "c"},
    ],
)
def test_create_document_validation(client, payload):
    r = client.post("/api/documents", json=payload)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert client.get("/api/health").json()["documents"] == 5


def test_duplicate_source_url_conflict_leaves_index_unchanged(client):
    body = dict(title="A", text="alpha beta", category="c", source_url="https://example.com/a")
    assert post(client, "/api/documents", **body).status_code == 201
    r = post(client, "/api/documents", **{**body, "title": "B", "text": "gamma delta"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_document"
    assert post(client, "/api/search/boolean", query="gamma").json()["matching_doc_ids"] == []
    assert client.get("/api/index/check").json()["consistent"] is True


# ------------------------------------------------------------------ ranked search
def test_ranked_search(client):
    r = post(client, "/api/search", query="machine learning")
    assert r.status_code == 200
    body = r.json()
    assert body["query"]["index_terms"] == ["machin", "learn"]
    assert body["results"][0]["doc_id"] == 3 and body["results"][0]["title"] == "Machine Learning"
    scores = [x["score"] for x in body["results"]]
    assert scores == sorted(scores, reverse=True) and all(0 < s <= 1 for s in scores)
    assert [x["rank"] for x in body["results"]] == list(range(1, len(scores) + 1))
    assert {x["doc_id"] for x in body["results"]} == {2, 3, 4}  # 'machin' appears in docs 2, 3, 4; 'learn' in 3
    assert body["total_results"] == 3 and body["took_ms"] >= 0
    assert body["query_vector"].keys() == {"machin", "learn"}


def test_ranked_search_explain_matches_cosine_formula(client):
    body = post(client, "/api/search", query="machine learning", explain=True).json()
    for item in body["results"]:
        e = item["explanation"]
        assert item["score"] == pytest.approx(e["dot_product"] / (e["query_norm"] * e["document_norm"]), abs=1e-12)
        assert sum(e["term_contributions"].values()) == pytest.approx(e["dot_product"])


def test_ranked_search_edge_queries(client):
    r = post(client, "/api/search", query="the and of").json()  # stop words only
    assert r["results"] == [] and r["total_results"] == 0 and "stop words" in r["message"]
    r = post(client, "/api/search", query="!!!").json()
    assert r["results"] == [] and r["message"]
    r = post(client, "/api/search", query="zzzzqq").json()
    assert r["results"] == [] and r["query"]["unknown_terms"] == ["zzzzqq"] and "None of the query terms" in r["message"]
    assert client.post("/api/search", json={"query": ""}).status_code == 422
    assert client.post("/api/search", json={"query": "   "}).status_code == 422
    assert client.post("/api/search", json={"query": "x" * 501}).status_code == 422
    assert client.post("/api/search", json={"query": "x", "page_size": 0}).status_code == 422


def test_ranked_search_pagination_and_category(client):
    p1 = post(client, "/api/search", query="programming python java data", page_size=1).json()
    p2 = post(client, "/api/search", query="programming python java data", page=2, page_size=1).json()
    assert p1["total_results"] == p2["total_results"] >= 2
    assert p1["results"][0]["rank"] == 1 and p2["results"][0]["rank"] == 2
    assert p1["results"][0]["doc_id"] != p2["results"][0]["doc_id"]
    cat = post(client, "/api/search", query="machine", category="AI/ML").json()
    assert [x["doc_id"] for x in cat["results"]] == [3] and cat["total_results"] == 1


# ------------------------------------------------------------------ boolean
@pytest.mark.parametrize(
    "query, expected",
    [
        ("machine AND learning", [3]),
        ("python OR java", [1, 2]),
        ("machine AND NOT hardware", [2, 3]),
        ("(python OR java) AND programming", [1, 2]),
        ("NOT security", [1, 2, 3, 4]),
        ("python OR java AND security", [1]),
        ("quantum", []),
    ],
)
def test_boolean_search(client, query, expected):
    r = post(client, "/api/search/boolean", query=query)
    assert r.status_code == 200
    body = r.json()
    assert body["matching_doc_ids"] == expected
    assert body["total_results"] == len(expected)
    assert [d["doc_id"] for d in body["results"]] == expected


def test_boolean_response_explains_evaluation(client):
    body = post(client, "/api/search/boolean", query="machine AND NOT hardware").json()
    assert body["parsed_expression"] == "(machine AND (NOT hardware))"
    assert body["index_terms"] == {"machine": ["machin"], "hardware": ["hardwar"]}
    assert [s["operation"] for s in body["steps"]] == ["LOOKUP", "LOOKUP", "NOT", "AND"]
    assert body["steps"][0]["description"] == "postings('machin') = [2, 3, 4] (df=3)"
    assert body["steps"][-1]["result_size"] == 2
    assert body["results"][0]["title"] == "Java Programming"
    assert post(client, "/api/search/boolean", query="quantum").json()["unknown_terms"] == ["quantum"]


@pytest.mark.parametrize("query", ["machine AND", "(machine", "machine learning", "mach*", "the", ")", "AND"])
def test_boolean_invalid_query_returns_400(client, query):
    r = post(client, "/api/search/boolean", query=query)
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "invalid_boolean_query" and err["message"]


def test_boolean_pagination(client):
    body = post(client, "/api/search/boolean", query="NOT security", page_size=2, page=2).json()
    assert body["total_results"] == 4 and [d["doc_id"] for d in body["results"]] == [3, 4]
    assert body["matching_doc_ids"] == [1, 2, 3, 4]


# ------------------------------------------------------------------ tolerant
def test_tolerant_prefix(client):
    body = post(client, "/api/search/tolerant", pattern="mach*").json()
    assert body["kind"] == "prefix"
    assert [m["term"] for m in body["matched_terms"]] == ["machine"]
    assert body["matched_terms"][0]["index_term"] == "machin"
    assert body["matched_terms"][0]["doc_ids"] == [2, 3, 4]
    assert body["matched_term_count"] == 1 and body["total_documents"] == 3
    assert [d["doc_id"] for d in body["documents"]] == [2, 3, 4]
    assert body["took_ms"] >= 0


def test_tolerant_wildcard(client):
    body = post(client, "/api/search/tolerant", pattern="comput*r").json()
    assert body["kind"] == "wildcard" and [m["term"] for m in body["matched_terms"]] == ["computer"]
    assert [d["doc_id"] for d in body["documents"]] == [4]
    body = post(client, "/api/search/tolerant", pattern="comput*").json()
    assert sorted(m["term"] for m in body["matched_terms"]) == ["computer", "computers"]
    assert body["total_documents"] == 2
    assert [d["doc_id"] for d in post(client, "/api/search/tolerant", pattern="p*thon").json()["documents"]] == [1]


def test_tolerant_no_match_limit_and_validation(client):
    body = post(client, "/api/search/tolerant", pattern="zzz*").json()
    assert body["matched_terms"] == [] and "No dictionary term" in body["message"]
    body = post(client, "/api/search/tolerant", pattern="*", max_expansions=2)
    assert body.status_code == 400 and body.json()["error"]["code"] == "invalid_pattern"
    body = post(client, "/api/search/tolerant", pattern="*a*", max_expansions=2).json()
    assert body["matched_term_count"] == 2 and body["truncated"] and body["total_matches"] > 2
    assert body["expansion_limit"] == 2 and "expansion limit" in body["message"]
    assert post(client, "/api/search/tolerant", pattern="a b*").status_code == 400
    assert post(client, "/api/search/tolerant", pattern="").status_code == 422
    assert post(client, "/api/search/tolerant", pattern="a*", max_expansions=0).status_code == 422
    assert post(client, "/api/search/tolerant", pattern="mach*", include_documents=False).json()["documents"] == []


def test_suggestions(client):
    body = client.get("/api/search/suggestions", params={"q": "mach"}).json()
    assert body["suggestions"] == [{"term": "machine", "document_count": 3}]
    body = client.get("/api/search/suggestions", params={"q": "data", "limit": 3}).json()
    assert [s["term"] for s in body["suggestions"]] == ["data"]
    assert client.get("/api/search/suggestions", params={"q": "qqqq"}).json()["suggestions"] == []
    assert client.get("/api/search/suggestions").status_code == 422
    assert client.get("/api/search/suggestions", params={"q": "a", "limit": 99}).status_code == 422


# ------------------------------------------------------------------ workbench
def test_workbench_preprocess(client):
    r = post(client, "/api/workbench/preprocess", text="The Quick, Brown Foxes!")
    assert r.status_code == 200
    assert r.json() == {
        "original": "The Quick, Brown Foxes!",
        "normalized": "the quick brown foxes",
        "tokens": ["the", "quick", "brown", "foxes"],
        "stop_words_removed": ["the"],
        "tokens_without_stopwords": ["quick", "brown", "foxes"],
        "stemmed_tokens": ["quick", "brown", "fox"],
        "lemmatized_tokens": ["quick", "brown", "fox"],
        "index_terms": ["quick", "brown", "fox"],
        "index_form": "stem",
    }
    empty = post(client, "/api/workbench/preprocess", text="").json()
    assert empty["tokens"] == [] and empty["index_terms"] == []
    assert client.post("/api/workbench/preprocess", json={}).status_code == 422


def test_workbench_incidence_matrix(client):
    body = post(client, "/api/workbench/incidence-matrix", terms=["python", "java", "machine", "the", "quantum"],
                document_ids=[1, 2, 3]).json()
    assert [d["doc_id"] for d in body["documents"]] == [1, 2, 3]
    rows = {r["term"]: r for r in body["rows"]}
    assert rows["python"]["row"] == [1, 0, 0] and rows["java"]["row"] == [0, 1, 0]
    assert rows["machine"]["row"] == [0, 1, 1] and rows["machine"]["document_frequency"] == 3
    assert rows["quantum"]["row"] == [0, 0, 0] and rows["quantum"]["document_frequency"] == 0
    assert body["ignored_terms"] == ["the"]
    # default: first documents of the corpus
    default = post(client, "/api/workbench/incidence-matrix", terms=["python"]).json()
    assert len(default["documents"]) == 5 and default["rows"][0]["row"] == [1, 0, 0, 0, 0]
    assert post(client, "/api/workbench/incidence-matrix", terms=["python"], document_ids=[1, 999]).status_code == 404
    assert post(client, "/api/workbench/incidence-matrix", terms=[]).status_code == 422


def test_workbench_inverted_index(client):
    body = client.get("/api/workbench/inverted-index", params={"term": "Python"}).json()
    assert body["term"] == "python" and body["document_frequency"] == 1
    assert body["postings"] == [{"doc_id": 1, "tf": 2, "title": "Python Programming"}]  # title + text
    body = client.get("/api/workbench/inverted-index", params={"term": "machines"}).json()
    assert body["term"] == "machin" and [p["doc_id"] for p in body["postings"]] == [2, 3, 4]
    assert body["stats"]["num_documents"] == 5
    assert client.get("/api/workbench/inverted-index", params={"term": "the"}).status_code == 400
    assert client.get("/api/workbench/inverted-index", params={"term": "two words"}).status_code == 400
    assert client.get("/api/workbench/inverted-index", params={"term": "quantum"}).json()["postings"] == []

    listing = client.get("/api/workbench/inverted-index", params={"page_size": 5}).json()
    terms = [t["term"] for t in listing["terms"]]
    assert len(terms) == 5 and terms == sorted(terms) and listing["total_terms"] > 5
    pref = client.get("/api/workbench/inverted-index", params={"prefix": "pro"}).json()
    assert [t["term"] for t in pref["terms"]] == ["processor", "program", "protect"]
    assert {t["term"]: t["document_frequency"] for t in pref["terms"]} == {"processor": 1, "program": 2, "protect": 1}


def test_workbench_tfidf_hand_calculated(client):
    body = post(client, "/api/workbench/tfidf", document_ids=[1], query="python").json()
    n = 5
    assert body["num_documents"] == n
    idf = math.log((n + 1) / (1 + 1)) + 1  # df(python) = 1
    q = body["query_terms"][0]
    assert q == {"term": "python", "tf": 1, "df": 1, "idf": pytest.approx(idf), "tfidf": pytest.approx(idf)}
    w = body["documents"][0]["query_term_weights"][0]
    assert w["tf"] == 2 and w["df"] == 1 and w["idf"] == pytest.approx(2.0986122886681098)
    assert w["tfidf"] == pytest.approx(2 * 2.0986122886681098)
    top = body["documents"][0]["top_terms"]
    assert top[0]["term"] == "python" and top == sorted(top, key=lambda t: -t["tfidf"])
    assert body["formulas"]["idf"] == "idf(t) = ln((N + 1) / (df(t) + 1)) + 1"

    unknown = post(client, "/api/workbench/tfidf", document_ids=[1], query="python quantum").json()
    assert unknown["unknown_terms"] == ["quantum"]
    assert post(client, "/api/workbench/tfidf", document_ids=[999]).status_code == 404
    assert post(client, "/api/workbench/tfidf", document_ids=[]).status_code == 422


def test_workbench_cosine(client):
    body = post(client, "/api/workbench/cosine", query="machine learning", top_k=2).json()
    assert body["query_terms"] == ["machin", "learn"]
    assert [d["rank"] for d in body["documents"]] == [1, 2]
    top = body["documents"][0]
    assert top["doc_id"] == 3 and top["title"] == "Machine Learning"
    assert top["cosine"] == pytest.approx(top["dot_product"] / (top["query_norm"] * top["document_norm"]), abs=1e-12)
    assert top["cosine"] == pytest.approx(
        sum(top["term_contributions"].values()) / (top["query_norm"] * top["document_norm"]), abs=1e-12)
    assert top["document_vector_shared_terms"].keys() == {"machin", "learn"}
    assert body["took_ms"] >= 0

    chosen = post(client, "/api/workbench/cosine", query="machine", document_ids=[1, 3]).json()
    assert [(d["doc_id"], d["cosine"] > 0) for d in chosen["documents"]] == [(3, True), (1, False)]
    zero = post(client, "/api/workbench/cosine", query="the of").json()
    assert zero["documents"] == [] and zero["query_vector"] == {}
    assert post(client, "/api/workbench/cosine", query="x", document_ids=[999]).status_code == 404
    # the same ranking is produced by /api/search and /api/workbench/cosine
    ranked = post(client, "/api/search", query="machine learning").json()["results"]
    full = post(client, "/api/workbench/cosine", query="machine learning", top_k=50).json()["documents"]
    assert [(r["doc_id"], r["score"]) for r in ranked] == [(d["doc_id"], d["cosine"]) for d in full]


# ------------------------------------------------------------------ index admin / persistence
def test_rebuild_index_endpoint_preserves_results(client):
    before = post(client, "/api/search", query="machine learning").json()["results"]
    r = client.post("/api/index/rebuild")
    assert r.status_code == 200 and r.json()["stats"]["num_documents"] == 5
    assert post(client, "/api/search", query="machine learning").json()["results"] == before
    assert client.get("/api/index/check").json()["consistent"] is True


def test_index_is_rebuilt_from_database_on_restart(client, api_settings):
    post(client, "/api/documents", title="Persistent", text="durable storage test", category="c")
    with TestClient(create_app(api_settings)) as fresh:  # new process-equivalent over the same SQLite file
        assert fresh.get("/api/health").json()["indexed_documents"] == 6
        assert post(fresh, "/api/search/boolean", query="durable").json()["matching_doc_ids"] == [6]


def test_unexpected_errors_do_not_leak_internals(api_settings):
    with TestClient(create_app(api_settings), raise_server_exceptions=False) as c:
        def boom(_text):
            raise RuntimeError("secret /home/someone/private.db failure")
        c.app.state.engine.preprocessor.analyze = boom
        r = c.post("/api/workbench/preprocess", json={"text": "x"})
        assert r.status_code == 500
        assert r.json() == {"error": {"code": "internal_error", "message": "An internal error occurred.", "details": None}}
        assert "secret" not in r.text and "private.db" not in r.text
