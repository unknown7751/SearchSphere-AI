"""Rocchio mathematics (hand-checked) and Rocchio-driven retrieval."""
import math

import pytest

from app.services import rocchio as rc
from app.services.advanced_retrieval import UnknownDocumentsError
from app.services.search_engine import SearchEngine

ORIGINAL = {"a": 1.0, "b": 2.0}
REL = [{"a": 2.0, "c": 4.0}, {"c": 2.0}]
NON = [{"b": 4.0, "d": 2.0}]


def run(**kw):
    kw.setdefault("normalize", False)
    return rc.rocchio(ORIGINAL, REL, NON, **kw)


# ------------------------------------------------------------------ the formula
def test_full_formula_by_hand():
    # a = 1*1 + .75/2*(2+0) - 0          = 1.75
    # b = 1*2 + 0            - .15/1*4   = 1.40
    # c = 0   + .75/2*(4+2)  - 0         = 2.25
    # d = 0   + 0            - .15/1*2   = -0.30  (clipped to 0)
    r = run()
    assert r.relevant_contribution == pytest.approx({"a": 0.75, "c": 2.25})
    assert r.non_relevant_contribution == pytest.approx({"b": 0.6, "d": 0.3})
    assert r.unclipped_vector == pytest.approx({"a": 1.75, "b": 1.4, "c": 2.25, "d": -0.3})
    assert r.updated_vector == pytest.approx({"a": 1.75, "b": 1.4, "c": 2.25})
    assert r.clipped_terms == ["d"]


def test_defaults_are_1_075_015():
    r = run()
    assert (r.alpha, r.beta, r.gamma) == (1.0, 0.75, 0.15)


def test_no_clipping_keeps_negative_weights():
    r = run(clip_negative=False)
    assert r.updated_vector["d"] == pytest.approx(-0.3)
    assert r.clipped_terms == []


def test_relevant_only():
    r = rc.rocchio(ORIGINAL, REL, [], normalize=False)
    assert r.non_relevant_contribution == {}
    assert r.updated_vector == pytest.approx({"a": 1.75, "b": 2.0, "c": 2.25})


def test_non_relevant_only():
    r = rc.rocchio(ORIGINAL, [], NON, normalize=False)
    assert r.relevant_contribution == {}
    assert r.updated_vector == pytest.approx({"a": 1.0, "b": 1.4})  # d would be negative -> clipped
    assert r.clipped_terms == ["d"]


def test_neither_set_returns_alpha_times_query():
    r = rc.rocchio(ORIGINAL, [], [], alpha=2.0, normalize=False)
    assert r.updated_vector == {"a": 2.0, "b": 4.0}


def test_custom_weights():
    r = run(alpha=0.5, beta=1.0, gamma=0.0)
    assert r.updated_vector == pytest.approx({"a": 0.5 + 1.0, "b": 1.0, "c": 3.0})
    assert r.non_relevant_contribution == {}  # gamma = 0 contributes nothing


def test_alpha_zero_drops_the_original_query():
    r = run(alpha=0.0, beta=1.0, gamma=0.0)
    assert "b" not in r.updated_vector


def test_zero_vectors_are_safe():
    r = rc.rocchio({}, [{}], [{}], normalize=True)
    assert r.updated_vector == {}
    r = rc.rocchio({}, [{"x": 3.0}], [], normalize=True)
    assert r.updated_vector == pytest.approx({"x": 0.75})
    # an all-zero relevant doc still counts towards |Dr|
    r = rc.rocchio({"a": 1.0}, [{"a": 2.0}, {}], [], normalize=False)
    assert r.relevant_contribution == pytest.approx({"a": 0.75})


def test_normalisation_scales_vectors_to_unit_length():
    r = rc.rocchio({"a": 3.0, "b": 4.0}, [{"a": 3.0, "b": 4.0}], [], alpha=1, beta=1, gamma=0, normalize=True)
    assert r.original_vector == pytest.approx({"a": 0.6, "b": 0.8})
    assert r.updated_vector == pytest.approx({"a": 1.2, "b": 1.6})
    assert math.isclose(sum(w * w for w in r.original_vector.values()), 1.0)


@pytest.mark.parametrize("weights", [(-1, 0.5, 0.1), (1, -0.1, 0), (1, 1, -2), (float("nan"), 1, 1), (1, float("inf"), 1)])
def test_invalid_weights_rejected(weights):
    a, b, g = weights
    with pytest.raises(rc.RocchioError):
        rc.rocchio(ORIGINAL, REL, NON, alpha=a, beta=b, gamma=g)


def test_dedupe_ids_and_overlap_detection():
    assert rc.dedupe_ids([3, 1, 3, 2, 1]) == [3, 1, 2]
    assert rc.dedupe_ids(None) == []
    assert rc.validate_feedback_sets([1, 1, 2], [3, 3]) == ([1, 2], [3])
    with pytest.raises(rc.RocchioError, match="both relevant and non-relevant"):
        rc.validate_feedback_sets([1, 2], [2, 3])


def test_top_terms_ordering():
    vec = {"b": 0.5, "a": 0.5, "c": 1.0, "n": -0.2, "m": -0.9}
    assert rc.top_terms(vec, 3) == [("c", 1.0), ("a", 0.5), ("b", 0.5)]
    assert rc.top_terms(vec, 5, positive=False) == [("m", -0.9), ("n", -0.2)]


# ------------------------------------------------------------------ retrieval with the modified vector
@pytest.fixture
def engine(preprocessor) -> SearchEngine:
    eng = SearchEngine(preprocessor=preprocessor)
    texts = {
        1: "banana apple apple",
        2: "banana cherry",
        3: "cherry date",
        4: "date elderberry",
        5: "fig grape",
    }
    for doc_id, text in texts.items():
        eng._index_document(doc_id, text)
    return eng


def ids(ranking):
    return [s.doc_id for s in ranking.ranked]


def test_no_feedback_equals_baseline_ranking(engine):
    s = engine.advanced.rocchio_search("banana")
    assert ids(s.ranking) == ids(s.baseline) == [2, 1]
    assert s.rocchio.relevant_ids == [] and not s.pseudo_feedback


def test_relevant_feedback_changes_the_ranking(engine):
    baseline = ids(engine.advanced.rocchio_search("banana").baseline)
    assert 3 not in baseline                       # doc 3 shares no term with the query
    s = engine.advanced.rocchio_search("banana", relevant_ids=[3])
    assert 3 in ids(s.ranking)                     # Rocchio pulled the query towards doc 3's vocabulary
    assert ids(s.ranking) != baseline
    assert ids(s.baseline) == baseline             # the baseline ranking is untouched
    assert set(s.rocchio.updated_vector) >= {"cherri", "date"} or len(s.rocchio.updated_vector) > 1


def test_non_relevant_feedback_demotes_documents(engine):
    # "banana apple apple" (doc 1) is judged non-relevant. With gamma = 1 and raw vectors its
    # banana weight (tf 1) cancels the query's banana weight, so a document that matched only
    # through "banana" drops out of the ranking while the cherry documents remain.
    base = engine.advanced.rocchio_search("banana cherry")
    assert 1 in ids(base.ranking)
    s = engine.advanced.rocchio_search(
        "banana cherry", non_relevant_ids=[1], alpha=1.0, gamma=1.0, normalize=False
    )
    assert "banana" in s.rocchio.clipped_terms or s.rocchio.updated_vector.get("banana", 0.0) == 0.0
    assert 1 not in ids(s.ranking)
    assert set(ids(s.ranking)) == {2, 3}


def test_duplicate_ids_are_deduplicated(engine):
    once = engine.advanced.rocchio_search("banana", relevant_ids=[3])
    dup = engine.advanced.rocchio_search("banana", relevant_ids=[3, 3, 3])
    assert dup.rocchio.relevant_ids == [3]
    assert dup.rocchio.updated_vector == pytest.approx(once.rocchio.updated_vector)


def test_unknown_document_ids_raise(engine):
    with pytest.raises(UnknownDocumentsError) as exc:
        engine.advanced.rocchio_search("banana", relevant_ids=[3, 999], non_relevant_ids=[1000])
    assert exc.value.missing == [999, 1000]


def test_document_in_both_sets_rejected(engine):
    with pytest.raises(rc.RocchioError):
        engine.advanced.rocchio_search("banana", relevant_ids=[3], non_relevant_ids=[3])


def test_query_with_only_stop_words_can_still_use_feedback(engine):
    s = engine.advanced.rocchio_search("the of", relevant_ids=[3])
    assert ids(s.ranking)[0] == 3 and s.original_vector == {}


def test_unknown_query_terms_are_reported_not_fatal(engine):
    s = engine.advanced.rocchio_search("banana zzzzz", relevant_ids=[3])
    assert s.unknown_terms == ["zzzzz"]


def test_pseudo_relevance_feedback_uses_top_baseline_documents(engine):
    s = engine.advanced.rocchio_search("banana", pseudo_feedback_docs=1)
    assert s.pseudo_feedback and s.rocchio.relevant_ids == [2]


def test_pseudo_feedback_ignored_when_explicit_ids_given(engine):
    s = engine.advanced.rocchio_search("banana", relevant_ids=[4], pseudo_feedback_docs=2)
    assert not s.pseudo_feedback and s.rocchio.relevant_ids == [4]


def test_ranked_doc_ids_for_every_mode(engine):
    for mode in ("tfidf", "expanded", "rocchio"):
        assert 2 in engine.advanced.ranked_doc_ids(mode, "banana")
    assert engine.advanced.ranked_doc_ids("boolean", "banana AND cherry") == [2]
