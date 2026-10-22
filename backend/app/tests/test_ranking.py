import math

import pytest

from app.services.inverted_index import InvertedIndex
from app.services.ranking import Ranker, TfidfModel, compute_idf, cosine_similarity
from app.tests.conftest import build_index

# Hand-computed constants for the 6-document SMALL_CORPUS (N = 6):
#   idf = ln((6+1)/(df+1)) + 1
IDF_DF1 = 2.252762968495368   # ln(7/2) + 1  (java, hardware, security)
IDF_DF2 = 1.8472978603872037  # ln(7/3) + 1  (machine, learning, programming)
IDF_DF3 = 1.5596157879354227  # ln(7/4) + 1  (python)
IDF_DF0 = 2.945910149055313   # ln(7/1) + 1  (unknown term)


@pytest.fixture
def model(small_index):
    return TfidfModel(small_index)


def test_idf_formula():
    assert compute_idf(6, 1) == pytest.approx(IDF_DF1, abs=1e-12)
    assert compute_idf(6, 2) == pytest.approx(IDF_DF2, abs=1e-12)
    assert compute_idf(6, 3) == pytest.approx(IDF_DF3, abs=1e-12)
    assert compute_idf(6, 0) == pytest.approx(IDF_DF0, abs=1e-12)
    assert compute_idf(0, 0) == 1.0  # empty collection: ln(1) + 1


def test_tf_df_idf_tfidf(model):
    assert model.tf("machine", 1) == 2
    assert model.tf("machine", 3) == 0
    assert model.df("machine") == 2
    assert model.idf("machine") == pytest.approx(IDF_DF2, abs=1e-12)
    assert model.tfidf("machine", 1) == pytest.approx(2 * IDF_DF2, abs=1e-12)
    assert model.tfidf("machine", 3) == 0.0
    assert model.idf("quantum") == pytest.approx(IDF_DF0, abs=1e-12)  # unknown term: df = 0
    assert model.df("quantum") == 0


def test_document_vector(model):
    assert model.document_vector(1) == {
        "machine": pytest.approx(2 * IDF_DF2),
        "learning": pytest.approx(IDF_DF2),
    }
    assert model.document_vector(999) == {}


def test_top_terms_ordered_by_weight(model):
    top = model.top_terms(4, 2)
    assert [t["term"] for t in top] == ["java", "programming"]  # 2.2528 > 1.8473 > python 1.5596
    assert top[0] == {"term": "java", "tf": 1, "df": 1, "idf": pytest.approx(IDF_DF1), "tfidf": pytest.approx(IDF_DF1)}


def test_vectors_update_when_collection_changes(small_index, model):
    before = model.idf("python")
    small_index.add_document(7, ["unrelated"])  # N grows 6 -> 7, df(python) unchanged
    assert model.idf("python") == pytest.approx(math.log(8 / 4) + 1)
    assert model.idf("python") != before
    assert model.document_vector(3)["python"] == pytest.approx(math.log(8 / 4) + 1)  # cache invalidated


def test_query_vector_and_unknown_terms(model):
    vec, unknown = model.query_vector(["python", "python", "quantum", "java"])
    assert vec == {"java": pytest.approx(IDF_DF1), "python": pytest.approx(2 * IDF_DF3)}
    assert unknown == ["quantum"]
    assert model.query_vector([]) == ({}, [])


def test_empty_vocabulary():
    model = TfidfModel(InvertedIndex())
    assert model.query_vector(["anything"]) == ({}, ["anything"])
    assert Ranker(model).rank(["anything"]).ranked == []
    assert model.document_vector(1) == {}


# ---------------------------------------------------------------- cosine


def test_cosine_hand_calculated():
    r = cosine_similarity({"a": 1.0, "b": 1.0}, {"a": 1.0})
    assert (r.dot, r.query_norm, r.doc_norm) == (1.0, pytest.approx(math.sqrt(2)), 1.0)
    assert r.score == pytest.approx(1 / math.sqrt(2), abs=1e-15)

    r = cosine_similarity({"a": 3.0, "b": 4.0}, {"a": 3.0, "b": 4.0})
    assert (r.dot, r.query_norm, r.doc_norm) == (25.0, 5.0, 5.0)
    assert r.score == pytest.approx(1.0)

    r = cosine_similarity({"a": 1.0, "b": 2.0}, {"a": 2.0, "b": 1.0})  # 4 / 5
    assert r.score == pytest.approx(0.8)


def test_cosine_orthogonal_and_zero_vectors():
    assert cosine_similarity({"a": 1.0}, {"b": 1.0}).score == 0.0
    for q, d in [({}, {"a": 1.0}), ({"a": 1.0}, {}), ({}, {}), ({"a": 0.0}, {"a": 1.0}), ({"a": 1.0}, {"a": 0.0})]:
        r = cosine_similarity(q, d)
        assert r.score == 0.0 and not math.isnan(r.score)


def test_cosine_is_scale_invariant():
    assert cosine_similarity({"a": 1.0, "b": 2.0}, {"a": 10.0, "b": 20.0}).score == pytest.approx(1.0)


def test_ranking_matches_independent_hand_calculation(model):
    result = Ranker(model).rank(["python", "programming"])
    assert [s.doc_id for s in result.ranked] == [3, 4, 6]
    s3, s4, s6 = result.ranked
    assert s3.score == pytest.approx(1.0)  # doc 3 has exactly the query's vector

    # doc 4 = {java, programming, python}; q = {programming, python}
    dot4 = IDF_DF2**2 + IDF_DF3**2
    qn = math.sqrt(dot4)
    dn4 = math.sqrt(IDF_DF1**2 + dot4)
    assert s4.dot == pytest.approx(dot4)
    assert s4.query_norm == pytest.approx(qn) and s4.doc_norm == pytest.approx(dn4)
    assert s4.score == pytest.approx(dot4 / (qn * dn4)) and s4.score == pytest.approx(0.7316, abs=1e-3)

    # doc 6 = {learning, python}
    dot6 = IDF_DF3**2
    dn6 = math.sqrt(IDF_DF2**2 + IDF_DF3**2)
    assert s6.score == pytest.approx(dot6 / (qn * dn6)) and s6.score == pytest.approx(0.4162, abs=1e-3)
    assert s4.term_contributions == {"programming": pytest.approx(IDF_DF2**2), "python": pytest.approx(IDF_DF3**2)}
    assert s3.score > s4.score > s6.score


def test_ranking_is_descending(model):
    scores = [s.score for s in Ranker(model).rank(["machine", "learning", "python"]).ranked]
    assert scores == sorted(scores, reverse=True) and len(scores) == 5


def test_deterministic_tie_breaking():
    index = InvertedIndex()
    for doc_id in (9, 4, 7):  # three identical documents, inserted out of order
        index.add_document(doc_id, ["alpha", "beta"])
    index.add_document(1, ["gamma"])
    ranker = Ranker(TfidfModel(index))
    first = [s.doc_id for s in ranker.rank(["alpha"]).ranked]
    assert first == [4, 7, 9]
    for _ in range(5):
        assert [s.doc_id for s in ranker.rank(["alpha"]).ranked] == first


def test_empty_and_unknown_queries(model):
    ranker = Ranker(model)
    assert ranker.rank([]).ranked == []
    r = ranker.rank(["quantum"])
    assert r.ranked == [] and r.unknown_terms == ["quantum"] and r.query_vector == {}


def test_unknown_terms_do_not_affect_ranking(model):
    ranker = Ranker(model)
    plain = [s.doc_id for s in ranker.rank(["python"]).ranked]
    with_unknown = [s.doc_id for s in ranker.rank(["python", "quantum"]).ranked]
    assert plain == with_unknown


def test_rank_restricted_to_chosen_documents_includes_zero_scores(model):
    result = Ranker(model).rank(["machine"], candidate_ids=[1, 3, 999])
    assert [(s.doc_id, s.score > 0) for s in result.ranked] == [(1, True), (3, False)]


def test_zero_vector_document_scores_zero():
    index = build_index()
    index.add_document(8, [])  # no terms -> zero vector
    result = Ranker(TfidfModel(index)).rank(["python"], candidate_ids=[8])
    assert result.ranked[0].score == 0.0 and result.ranked[0].doc_norm == 0.0
