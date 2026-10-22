"""Phase 2 API: search explanations, expansion, Rocchio, workbench, evaluation."""
import pytest

from app.database.connection import connect
from app.database.evaluation import list_queries, load_evaluation_file, seed_evaluation
from app.database.schema import init_db
from app.database.seed import load_seed_file, seed_database


def post(client, url, **body):
    return client.post(url, json=body)


def ids(response):
    return [r["doc_id"] for r in response.json()["results"]]


# Seed corpus: document ids follow the order of seed_documents.json (seed-030 -> id 30 ...).
ML_RELEVANT = [30, 31, 32, 39, 40, 41, 44]


def test_seed_ids_match_expectations(seeded_client):
    assert seeded_client.get("/api/documents/30").json()["title"] == "Introduction to Machine Learning"
    assert seeded_client.get("/api/documents/39").json()["title"] == "Overfitting and Regularisation"


# ------------------------------------------------------------------ search explanation
def test_search_explanation_exposes_matching_terms(client):
    body = post(client, "/api/search", query="machine learning", explain=True).json()
    exp = body["results"][0]["explanation"]
    assert exp["matching_terms"], "expected matching terms"
    for t in exp["matching_terms"]:
        assert t["tfidf"] == pytest.approx(t["tf"] * t["idf"])
        assert t["contribution"] == pytest.approx(t["query_weight"] * t["tfidf"])
        assert t["tf"] >= 1 and t["df"] >= 1 and t["word"]
    assert sum(t["contribution"] for t in exp["matching_terms"]) == pytest.approx(exp["dot_product"])
    assert {t["term"] for t in exp["matching_terms"]} == set(exp["term_contributions"])


def test_explanation_absent_by_default(client):
    body = post(client, "/api/search", query="machine learning").json()
    assert all(r.get("explanation") is None for r in body["results"])


# ------------------------------------------------------------------ expanded search
def test_expanded_search(seeded_client):
    r = post(seeded_client, "/api/search/expanded", query="machine learning", explain=True)
    assert r.status_code == 200, r.text
    body = r.json()
    exp = body["expansion"]
    assert exp["original_query"] == "machine learning"
    assert exp["final_expanded_query"].startswith("machine learning ")
    assert exp["expanded_terms"] and len(exp["expanded_terms"]) <= 5
    assert set(exp["expanded_terms"][0]) >= {"term", "display", "score", "support", "document_frequency", "idf"}
    for t in exp["expanded_terms"]:
        assert t["term"] in body["query_vector"]  # the expanded vector is what was ranked
    again = post(seeded_client, "/api/search/expanded", query="machine learning").json()["expansion"]
    assert again == post(seeded_client, "/api/search/expanded", query="machine learning").json()["expansion"]


def test_expanded_search_with_unknown_query(seeded_client):
    body = post(seeded_client, "/api/search/expanded", query="qqqqzzzz").json()
    assert body["results"] == [] and body["expansion"]["expanded_terms"] == []
    assert body["expansion"]["message"]


@pytest.mark.parametrize(
    "payload",
    [{"query": " "}, {"query": "ml", "feedback_docs": 0}, {"query": "ml", "max_expansion_terms": 99}, {"query": "ml", "expansion_weight": 0}],
)
def test_expanded_search_validation(client, payload):
    assert client.post("/api/search/expanded", json=payload).status_code == 422


# ------------------------------------------------------------------ Rocchio search
def test_rocchio_search_changes_retrieval(seeded_client):
    base = post(seeded_client, "/api/search", query="machine learning", page_size=100)
    r = post(seeded_client, "/api/search/rocchio", query="machine learning", page_size=100,
             relevant_doc_ids=[30, 31, 39], non_relevant_doc_ids=[2])
    assert r.status_code == 200, r.text
    body = r.json()
    assert ids(r) != ids(base)
    assert 39 in ids(r)
    assert body["rocchio"]["relevant_documents"] == [30, 31, 39]
    assert body["rocchio"]["non_relevant_documents"] == [2]
    assert (body["rocchio"]["alpha"], body["rocchio"]["beta"], body["rocchio"]["gamma"]) == (1.0, 0.75, 0.15)
    assert body["rocchio"]["top_positive_terms"] and body["rocchio"]["top_negative_terms"]
    # the modified vector (not the typed query) was ranked
    assert len(body["query_vector"]) > len(base.json()["query_vector"])


def test_rocchio_search_without_feedback_equals_plain_search(seeded_client):
    base = post(seeded_client, "/api/search", query="machine learning", page_size=100)
    r = post(seeded_client, "/api/search/rocchio", query="machine learning", page_size=100)
    assert ids(r) == ids(base)


def test_rocchio_custom_weights_matter(seeded_client):
    kw = dict(query="machine learning", relevant_doc_ids=[39], page_size=100)
    low = post(seeded_client, "/api/search/rocchio", beta=0.0, **kw)
    high = post(seeded_client, "/api/search/rocchio", beta=5.0, **kw)
    assert low.json()["rocchio"]["beta"] == 0.0 and high.json()["rocchio"]["beta"] == 5.0
    assert ids(low) != ids(high)


def test_rocchio_search_errors(seeded_client):
    c = seeded_client
    r = post(c, "/api/search/rocchio", query="machine learning", relevant_doc_ids=[30, 99999])
    assert r.status_code == 404 and r.json()["error"]["code"] == "document_not_found"
    assert r.json()["error"]["details"]["missing"] == [99999]
    r = post(c, "/api/search/rocchio", query="machine learning", relevant_doc_ids=[30], non_relevant_doc_ids=[30])
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_rocchio_input"
    for bad in ({"relevant_doc_ids": [0]}, {"relevant_doc_ids": [-3]}, {"relevant_doc_ids": ["x"]}, {"alpha": -1},
                {"beta": -0.5}, {"gamma": "high"}, {"gamma": -2}):
        assert post(c, "/api/search/rocchio", query="machine learning", **bad).status_code == 422, bad
    assert post(c, "/api/search/rocchio", query="").status_code == 422


# ------------------------------------------------------------------ workbench
def test_workbench_query_expansion(seeded_client):
    r = post(seeded_client, "/api/workbench/query-expansion", query="machine learning", top_k=5)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["preprocessing"]["index_terms"] == ["machin", "learn"]
    assert b["original_query"] == "machine learning"
    assert b["final_expanded_query"].startswith("machine learning")
    assert b["feedback_documents"] and b["candidate_terms"]
    assert [t["term"] for t in b["expanded_terms"]] == [c["term"] for c in b["candidate_terms"] if c["selected"]]
    assert len(b["ranking_before"]) <= 5 and len(b["ranking_after"]) <= 5
    assert all({"rank", "doc_id", "title", "score", "baseline_rank", "rank_change"} <= set(row) for row in b["ranking_after"])


def test_workbench_rocchio_exposes_the_arithmetic(seeded_client):
    r = post(seeded_client, "/api/workbench/rocchio", query="machine learning", relevant_doc_ids=[30, 31],
             non_relevant_doc_ids=[2], alpha=1.0, beta=0.75, gamma=0.15)
    assert r.status_code == 200, r.text
    b = r.json()
    assert "alpha * q0" in b["formula"]
    assert b["parameters"] == {"alpha": 1.0, "beta": 0.75, "gamma": 0.15, "normalized": True}
    assert [d["doc_id"] for d in b["feedback_documents"]["relevant"]] == [30, 31]
    assert b["term_calculations"]
    for row in b["term_calculations"]:
        expected = row["alpha_x_original"] + row["relevant_contribution"] - row["non_relevant_contribution"]
        assert row["before_clipping"] == pytest.approx(expected)
        assert row["updated"] == pytest.approx(max(expected, 0.0))
    assert set(b["original_query_vector"]) == {"machin", "learn"}
    assert b["vector_sizes"]["updated"] > b["vector_sizes"]["original"]
    top = b["similarity"][0]
    assert top["cosine"] == pytest.approx(top["dot_product"] / (top["query_norm"] * top["document_norm"]))
    assert len(b["updated_query_vector"]) <= 15  # vectors are truncated for the response
    assert [x["doc_id"] for x in b["ranking"]] == [x["doc_id"] for x in b["similarity"]]


def test_workbench_rocchio_with_no_feedback_and_pseudo_feedback(seeded_client):
    b = post(seeded_client, "/api/workbench/rocchio", query="machine learning").json()
    assert b["input"]["relevant_doc_ids"] == [] and not b["input"]["pseudo_feedback"]
    assert [r["doc_id"] for r in b["ranking"]] == [r["doc_id"] for r in b["ranking_before"]]
    p = post(seeded_client, "/api/workbench/rocchio", query="machine learning", pseudo_feedback_docs=2).json()
    assert p["input"]["pseudo_feedback"] and len(p["input"]["relevant_doc_ids"]) == 2


def test_workbench_relevance_feedback(seeded_client):
    r = post(seeded_client, "/api/workbench/relevance-feedback", query="machine learning", relevant_doc_ids=[30, 31, 39])
    assert r.status_code == 200, r.text
    b = r.json()
    assert {"original_query_vector", "relevant_contribution", "non_relevant_contribution", "updated_query_vector",
            "top_positive_terms", "ranking_before", "ranking_after"} <= set(b)
    assert b["non_relevant_contribution"] == {}
    assert b["ranking_before"] != b["ranking_after"]
    assert {30, 31, 39} <= {x["doc_id"] for x in b["ranking_after"]}


def test_workbench_relevance_feedback_errors(seeded_client):
    c = seeded_client
    r = post(c, "/api/workbench/relevance-feedback", query="machine learning")
    assert r.status_code == 400 and r.json()["error"]["code"] == "no_feedback_documents"
    assert post(c, "/api/workbench/relevance-feedback", query="x", relevant_doc_ids=[5000]).status_code == 404
    assert post(c, "/api/workbench/relevance-feedback", query="x", relevant_doc_ids=[1], gamma=-1).status_code == 422
    assert post(c, "/api/workbench/rocchio", query="x", non_relevant_doc_ids=[7777]).status_code == 404


# ------------------------------------------------------------------ evaluation
def test_evaluation_run_with_explicit_judgments(seeded_client):
    r = post(seeded_client, "/api/evaluation/run", query="machine learning", top_k=5, relevant_doc_ids=ML_RELEVANT)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["relevance_source"] == "request" and b["mode"] == "tfidf" and b["top_k"] == 5
    assert len(b["retrieved_doc_ids"]) == 5
    hits = len(b["relevant_retrieved_doc_ids"])
    assert b["precision"] == pytest.approx(hits / 5) == pytest.approx(b["precision_at_k"])
    assert b["recall"] == pytest.approx(hits / 7) == pytest.approx(b["recall_at_k"])
    assert b["f1"] == pytest.approx(2 * b["precision"] * b["recall"] / (b["precision"] + b["recall"]))
    assert 0 < b["average_precision"] <= 1


def test_evaluation_run_uses_dataset_when_no_ids_given(seeded_client):
    b = post(seeded_client, "/api/evaluation/run", query="machine learning").json()
    assert b["relevance_source"] == "dataset" and b["relevant_doc_ids"] == ML_RELEVANT


@pytest.mark.parametrize("mode", ["tfidf", "expanded", "rocchio"])
def test_evaluation_run_every_ranked_mode(seeded_client, mode):
    b = post(seeded_client, "/api/evaluation/run", query="neural networks", mode=mode, top_k=10).json()
    assert b["mode"] == mode and 0 <= b["average_precision"] <= 1 and b["total_ranked"] > 0


def test_evaluation_boolean_mode(seeded_client):
    r = post(seeded_client, "/api/evaluation/run", query="sorting AND algorithms", mode="boolean", relevant_doc_ids=[16, 19])
    assert r.status_code == 200 and r.json()["retrieved_doc_ids"] == [16]
    assert r.json()["recall"] == 0.5
    r = post(seeded_client, "/api/evaluation/run", query="machine learning", mode="boolean", relevant_doc_ids=[30])
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_boolean_query"


def test_oracle_feedback_improves_average_precision(seeded_client):
    kw = dict(query="machine learning", relevant_doc_ids=ML_RELEVANT, top_k=10)
    plain = post(seeded_client, "/api/evaluation/run", mode="tfidf", **kw).json()
    fed = post(seeded_client, "/api/evaluation/run", mode="rocchio", feedback_relevant_doc_ids=[30, 31],
               feedback_non_relevant_doc_ids=[2], **kw).json()
    assert fed["average_precision"] > plain["average_precision"]


def test_evaluation_run_errors(seeded_client):
    c = seeded_client
    r = post(c, "/api/evaluation/run", query="completely unknown query")
    assert r.status_code == 400 and r.json()["error"]["code"] == "no_relevance_judgments"
    assert post(c, "/api/evaluation/run", query="q", relevant_doc_ids=[]).status_code == 400
    r = post(c, "/api/evaluation/run", query="q", relevant_doc_ids=[1, 424242])
    assert r.status_code == 404 and r.json()["error"]["details"]["missing"] == [424242]
    for bad in ({"top_k": 0}, {"top_k": -1}, {"top_k": 1000}, {"mode": "magic"}, {"relevant_doc_ids": [0]}, {"alpha": -1}):
        assert post(c, "/api/evaluation/run", query="machine learning", **bad).status_code == 422, bad
    assert post(c, "/api/evaluation/run").status_code == 422


def test_evaluation_k_larger_than_result_count(seeded_client):
    b = post(seeded_client, "/api/evaluation/run", query="sorting algorithms", relevant_doc_ids=[16], top_k=100).json()
    assert b["precision_at_k"] == pytest.approx(len(b["relevant_retrieved_doc_ids"]) / 100)
    assert len(b["retrieved_doc_ids"]) == b["total_ranked"] < 100


def test_evaluation_map_over_dataset(seeded_client):
    r = post(seeded_client, "/api/evaluation/map", top_k=10)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["query_count"] == 10 == len(b["per_query"])
    aps = [q["average_precision"] for q in b["per_query"]]
    assert b["mean_average_precision"] == pytest.approx(sum(aps) / 10)
    assert b["map_calculation"].endswith(f"= {b['mean_average_precision']:.4f}")
    q = b["per_query"][0]
    single = post(seeded_client, "/api/evaluation/run", query=q["query"], top_k=10).json()
    assert single["average_precision"] == pytest.approx(q["average_precision"])
    assert all(x["relevance_source"] == "dataset" for x in b["per_query"])


def test_evaluation_map_with_supplied_queries_matches_hand_calculation(seeded_client):
    # Boolean results come back in id order, so AP is exactly computable by hand:
    #   "sorting AND algorithms" -> [16];  relevant {16, 19}  => AP = (1/1) / 2 = 0.5
    #   "encryption" -> ids ascending, 73 first;  relevant {73} => AP = 1/1 = 1.0
    r = post(seeded_client, "/api/evaluation/map", mode="boolean", top_k=5, queries=[
        {"query": "sorting AND algorithms", "relevant_doc_ids": [16, 19]},
        {"query": "encryption", "relevant_doc_ids": [73]},
    ])
    assert r.status_code == 200, r.text
    b = r.json()
    assert [q["average_precision"] for q in b["per_query"]] == pytest.approx([0.5, 1.0])
    assert b["mean_average_precision"] == pytest.approx(0.75)
    assert b["map_calculation"] == "(0.5000 + 1.0000) / 2 = 0.7500"


def test_evaluation_map_modes_and_errors(seeded_client):
    c = seeded_client
    for mode in ("expanded", "rocchio"):
        assert post(c, "/api/evaluation/map", mode=mode).json()["query_count"] == 10
    assert post(c, "/api/evaluation/map", queries=[]).status_code == 422
    assert post(c, "/api/evaluation/map", queries=[{"query": "x", "relevant_doc_ids": []}]).status_code == 422
    assert post(c, "/api/evaluation/map", queries=[{"query": "x", "relevant_doc_ids": [9999999]}]).status_code == 404
    assert post(c, "/api/evaluation/map", top_k=0).status_code == 422


def test_evaluation_map_without_dataset_is_404(client):
    r = post(client, "/api/evaluation/map")
    assert r.status_code == 404 and r.json()["error"]["code"] == "evaluation_dataset_empty"
    assert client.get("/api/evaluation/dataset").json() == {"query_count": 0, "queries": []}


def test_evaluation_dataset_endpoint(seeded_client):
    b = seeded_client.get("/api/evaluation/dataset").json()
    assert b["query_count"] == 10
    ml = next(q for q in b["queries"] if q["query"] == "machine learning")
    assert ml["relevant_doc_ids"] == ML_RELEVANT


def test_workbench_evaluation(seeded_client):
    r = post(seeded_client, "/api/workbench/evaluation", query="machine learning", top_k=5)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["counts"]["retrieved"] == 5 and b["counts"]["relevant_total"] == 7
    rows = b["ranked_documents"]
    assert [x["rank"] for x in rows] == [1, 2, 3, 4, 5]
    assert rows[-1]["relevant_so_far"] == b["counts"]["relevant_retrieved"]
    assert b["metrics"]["precision_at_k"] == pytest.approx(rows[-1]["precision_at_rank"])
    assert "=" in b["calculations"]["average_precision"] and b["average_precision_steps"]
    assert set(b["missed_relevant_doc_ids"]).isdisjoint({x["doc_id"] for x in rows if x["relevant"]})
    assert post(seeded_client, "/api/workbench/evaluation", query="nothing known").status_code == 400


# ------------------------------------------------------------------ dataset integrity
def test_evaluation_dataset_references_real_seed_documents(tmp_path):
    seed_ids = {d["id"] for d in load_seed_file()}
    queries = load_evaluation_file()
    assert len(queries) >= 8
    for q in queries:
        assert set(q["relevant"]) <= seed_ids, q["query"]
        assert len(set(q["relevant"])) == len(q["relevant"])
    conn = connect(tmp_path / "e.db")
    init_db(conn)
    seed_database(conn)
    first = seed_evaluation(conn)
    assert first["missing_documents"] == 0 and first["judgments"] == sum(len(q["relevant"]) for q in queries)
    assert seed_evaluation(conn) == first  # idempotent
    assert conn.execute("SELECT COUNT(*) FROM evaluation_queries").fetchone()[0] == len(queries)
    assert len(list_queries(conn)) == len(queries)
    # deleting a judged document cascades to its judgments
    conn.execute("DELETE FROM documents WHERE external_id = 'seed-030'")
    ml = next(q for q in list_queries(conn) if q.query == "machine learning")
    assert 30 not in ml.relevant_doc_ids and len(ml.relevant_doc_ids) == 6
    conn.close()


def test_seed_evaluation_skips_missing_documents(tmp_path):
    conn = connect(tmp_path / "e.db")
    init_db(conn)
    result = seed_evaluation(conn)  # no documents at all
    assert result["judgments"] == 0 and result["missing_documents"] > 0
    assert list_queries(conn) == []
    conn.close()


# ------------------------------------------------------------------ Phase 1 compatibility
def test_all_endpoints_registered(client):
    spec = client.get("/openapi.json").json()["paths"]
    for path in ("/api/health", "/api/documents", "/api/documents/upload", "/api/search", "/api/search/expanded",
                 "/api/search/rocchio", "/api/search/boolean", "/api/search/tolerant", "/api/evaluation/run",
                 "/api/evaluation/map", "/api/evaluation/dataset", "/api/workbench/query-expansion",
                 "/api/workbench/rocchio", "/api/workbench/relevance-feedback", "/api/workbench/evaluation",
                 "/api/workbench/tfidf", "/api/workbench/cosine"):
        assert path in spec, path
