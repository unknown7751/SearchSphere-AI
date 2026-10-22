"""Query expansion: terms must come from the corpus, deterministically."""
import pytest

from app.services.search_engine import SearchEngine

CORPUS = {
    1: "neural network training data",
    2: "neural network training model",
    3: "neural network layers training",
    4: "gardening tomato soil",
    5: "tomato soil water",
    6: "quokka zebra",
}


@pytest.fixture
def engine(preprocessor) -> SearchEngine:
    eng = SearchEngine(preprocessor=preprocessor)
    for doc_id, text in CORPUS.items():
        eng._index_document(doc_id, text)
    return eng


def expand(engine, query, **kw):
    return engine.advanced.expanded_search(query, **kw)


def test_valid_query_adds_corpus_supported_term(engine):
    result = expand(engine, "neural network").expansion
    assert [c.term for c in result.expanded_terms] == ["train"]
    assert result.expanded_terms[0].display == "training"
    assert result.expanded_terms[0].support == 3
    assert result.final_query_text("neural network") == "neural network training"
    assert result.original_terms == ["neural", "network"]


def test_terms_seen_in_only_one_document_are_not_invented_as_evidence(engine):
    # 'data', 'model' and 'layers' each occur in a single document (df = 1) -> rejected
    result = expand(engine, "neural network").expansion
    assert not {"data", "model", "layer"} & {c.term for c in result.candidates}


def test_original_terms_are_never_added_again(engine):
    result = expand(engine, "neural network").expansion
    assert not {"neural", "network"} & {c.term for c in result.candidates}


def test_unknown_query_terms_give_no_expansion(engine):
    result = expand(engine, "zzzzqq").expansion
    assert result.expanded_terms == [] and result.feedback_doc_ids == []
    assert "nothing to learn" in result.reason
    assert result.expanded_vector == {}
    assert expand(engine, "zzzzqq").ranking.ranked == []


def test_stop_word_only_query(engine):
    result = expand(engine, "the of and").expansion
    assert result.expanded_terms == [] and result.reason


def test_no_expansion_candidates_when_corpus_gives_no_support(engine):
    result = expand(engine, "quokka").expansion        # only doc 6, whose other term has df = 1
    assert result.feedback_doc_ids == [6]
    assert result.expanded_terms == []
    assert result.reason and "supported" in result.reason
    # without expansion the expanded ranking equals the baseline
    search = expand(engine, "quokka")
    assert [s.doc_id for s in search.ranking.ranked] == [s.doc_id for s in search.baseline.ranked] == [6]


def test_output_is_deterministic(engine):
    first = expand(engine, "neural network").expansion
    for _ in range(3):
        again = expand(engine, "neural network").expansion
        assert [(c.term, c.score) for c in again.candidates] == [(c.term, c.score) for c in first.candidates]
        assert again.expanded_vector == first.expanded_vector


def test_expanded_vector_weights(engine):
    result = expand(engine, "neural network", expansion_weight=0.5).expansion
    term = result.expanded_terms[0]
    assert result.expanded_vector["train"] == pytest.approx(0.5 * term.idf)
    for original in ("neural", "network"):
        assert result.expanded_vector[original] == result.original_vector[original]


def test_max_terms_limits_selection(engine):
    corpus_engine = engine
    corpus_engine._index_document(7, "tomato soil water compost")
    one = expand(corpus_engine, "tomato", max_terms=1).expansion
    two = expand(corpus_engine, "tomato", max_terms=2).expansion
    assert len(one.expanded_terms) == 1 and len(two.expanded_terms) == 2
    assert two.expanded_terms[0].term == one.expanded_terms[0].term


def test_expansion_changes_ranking_through_the_vector(engine):
    search = expand(engine, "neural network")
    assert "train" in search.ranking.query_vector
    assert "train" not in search.baseline.query_vector


def test_display_form_round_trips_through_the_preprocessor(engine):
    for term in engine.index.vocabulary():
        word = engine.index.display_form(term)
        assert engine.preprocessor.index_terms(word) == [term]
