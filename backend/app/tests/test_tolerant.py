import pytest

from app.services.inverted_index import InvertedIndex
from app.services.tolerant_retrieval import PatternError, TolerantRetriever

# (index term, surface form) pairs per document
DOCS = {
    1: [("comput", "computer"), ("comput", "computing"), ("algorithm", "algorithm"), ("python", "python")],
    2: [("comput", "computer"), ("comput", "computers"), ("python", "python"), ("program", "programming"),
        ("program", "program"), ("process", "process"), ("processor", "processor"), ("protocol", "protocol"),
        ("secur", "secure"), ("secur", "security")],
    3: [("machin", "machine"), ("machin", "machines"), ("secur", "security")],
}


@pytest.fixture
def retriever():
    index = InvertedIndex()
    for doc_id, pairs in DOCS.items():
        index.add_document(doc_id, [t for t, _ in pairs], [s for _, s in pairs])
    return TolerantRetriever(index, default_limit=50)


def words(result):
    return sorted(m.term for m in result.matched_terms)


@pytest.mark.parametrize(
    "pattern, kind, expected",
    [
        ("comp*", "prefix", ["computer", "computers", "computing"]),
        ("mach*", "prefix", ["machine", "machines"]),
        ("secur*", "prefix", ["secure", "security"]),
        ("pro*", "prefix", ["process", "processor", "program", "programming", "protocol"]),
        ("comput*r", "wildcard", ["computer"]),
        ("p*thon", "wildcard", ["python"]),
        ("algor*hm", "wildcard", ["algorithm"]),
        ("pro*r", "wildcard", ["processor"]),
        ("*ing", "wildcard", ["computing", "programming"]),
        ("*uter*", "wildcard", ["computer", "computers"]),
        ("p*o*", "wildcard", ["process", "processor", "program", "programming", "protocol", "python"]),
        ("machine", "exact", ["machine"]),
        ("COMPUT*R", "wildcard", ["computer"]),  # case-insensitive
        ("computer*", "prefix", ["computer", "computers"]),  # '*' matches zero characters
        ("c*r*", "wildcard", ["computer", "computers"]),
    ],
)
def test_patterns(retriever, pattern, kind, expected):
    result = retriever.search(pattern)
    assert result.kind == kind
    assert words(result) == expected
    assert result.total_matches == len(expected)
    assert not result.truncated


def test_documents_are_those_containing_the_exact_word(retriever):
    r = retriever.search("comput*r")
    assert r.doc_ids == [1, 2]  # 'computer' occurs in docs 1 and 2
    r = retriever.search("computers")
    assert r.doc_ids == [2]  # 'computing' / 'computer' docs are NOT included for the exact surface 'computers'
    assert retriever.search("secur*").doc_ids == [2, 3]


def test_matched_terms_map_back_to_index_term(retriever):
    r = retriever.search("comput*")
    assert {m.term: m.index_term for m in r.matched_terms} == {
        "computer": "comput", "computers": "comput", "computing": "comput"}


def test_no_matches(retriever):
    r = retriever.search("xyz*")
    assert r.matched_terms == [] and r.total_matches == 0 and r.doc_ids == []
    assert retriever.search("q*z").total_matches == 0
    assert retriever.search("nonexistentword").matched_terms == []


def test_expansion_limit_keeps_most_frequent(retriever):
    r = retriever.search("pro*", max_expansions=2)
    assert len(r.matched_terms) == 2 and r.truncated and r.total_matches == 5
    # all five terms occur in exactly one document, so ties fall back to alphabetical order
    assert [m.term for m in r.matched_terms] == ["process", "processor"]
    r = retriever.search("comp*", max_expansions=1)
    assert [m.term for m in r.matched_terms] == ["computer"]  # df=2 beats computers/computing (df=1)


def test_strategies_differ(retriever):
    assert "binary search" in retriever.search("mach*").strategy
    assert "prefix, then pattern filter" in retriever.search("comput*r").strategy
    assert "scan" in retriever.search("*ing").strategy


@pytest.mark.parametrize("bad", ["", "   ", "*", "**", "a b*", "mach-ine*", "pro?", "a_b*"])
def test_invalid_patterns(retriever, bad):
    with pytest.raises(PatternError):
        retriever.search(bad)


def test_suggestions(retriever):
    assert retriever.suggest("comp", 5) == [("computer", 2), ("computers", 1), ("computing", 1)]
    assert retriever.suggest("find the mach") == [("machine", 1), ("machines", 1)]
    assert retriever.suggest("zzz") == []
    assert retriever.suggest("") == []
    assert len(retriever.suggest("p", 3)) == 3
