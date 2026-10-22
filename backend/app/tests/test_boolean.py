import pytest

from app.services.boolean_retrieval import (
    BooleanQueryError,
    BooleanRetriever,
    difference,
    incidence_matrix,
    intersect,
    parse_boolean_query,
    node_to_string,
    tokenize_query,
    union,
)

STOP = {"the", "of", "is"}


def resolve(word: str) -> list[str]:
    word = word.lower()
    return [] if word in STOP else [word]


@pytest.fixture
def retriever(small_index):
    return BooleanRetriever(small_index, resolve)


@pytest.mark.parametrize(
    "query, expected",
    [
        ("machine AND learning", [1]),
        ("python OR java", [3, 4, 6]),
        ("machine AND NOT hardware", [1]),
        ("(python OR java) AND programming", [3, 4]),
        ("NOT security", [1, 2, 3, 4, 6]),
        ("python", [3, 4, 6]),
        ("python AND programming AND java", [4]),
        ("machine OR security OR hardware", [1, 2, 5]),
        ("NOT NOT python", [3, 4, 6]),
        ("machine and LEARNING", [1]),  # operators and terms are case-insensitive
    ],
)
def test_basic_queries(retriever, query, expected):
    assert retriever.search(query).doc_ids == expected


def test_not_is_relative_to_searchable_corpus(small_index):
    r = BooleanRetriever(small_index, resolve)
    assert r.search("NOT python").doc_ids == [1, 2, 5]
    small_index.remove_document(5)
    assert r.search("NOT python").doc_ids == [1, 2]
    small_index.add_document(7, ["newterm"])
    assert r.search("NOT python").doc_ids == [1, 2, 7]


def test_precedence_not_over_and_over_or(retriever):
    # AND binds tighter than OR: python OR (java AND security) = python docs
    assert retriever.search("python OR java AND security").doc_ids == [3, 4, 6]
    # left-to-right evaluation would have given ((python OR java) AND security) = []
    assert retriever.search("(python OR java) AND security").doc_ids == []
    # NOT binds tighter than AND: (NOT python) AND learning = {1,2,5} & {1,6}
    assert retriever.search("NOT python AND learning").doc_ids == [1]
    # NOT binds tighter than AND, not the whole conjunction: NOT (python AND learning) = all but 6
    assert retriever.search("NOT (python AND learning)").doc_ids == [1, 2, 3, 4, 5]


@pytest.mark.parametrize(
    "query, rendering",
    [
        ("a OR b AND c", "(a OR (b AND c))"),
        ("a AND b OR c", "((a AND b) OR c)"),
        ("NOT a AND b", "((NOT a) AND b)"),
        ("machine AND NOT hardware", "(machine AND (NOT hardware))"),
        ("(a OR b) AND c", "((a OR b) AND c)"),
        ("a AND b AND c", "((a AND b) AND c)"),
    ],
)
def test_parse_tree_shape(query, rendering):
    assert node_to_string(parse_boolean_query(query, resolve)) == rendering


def test_nested_expressions(retriever):
    assert retriever.search("((python OR java) AND (NOT learning)) OR security").doc_ids == [3, 4, 5]
    assert retriever.search("(((machine)))").doc_ids == [1, 2]
    assert retriever.search("NOT (machine OR (python AND NOT java))").doc_ids == [4, 5]


@pytest.mark.parametrize(
    "query, fragment",
    [
        ("", "empty"),
        ("   ", "empty"),
        ("machine AND", "end of query"),
        ("AND machine", "Unexpected AND"),
        ("machine AND OR learning", "Unexpected OR"),
        ("(machine", "Missing closing"),
        ("machine)", "Unmatched ')'"),
        ("()", "Unexpected ')'"),
        ("machine learning", "Missing operator"),
        ("machine (learning)", "Missing operator"),
        ("NOT", "end of query"),
        ("mach*", "not supported in Boolean"),
        ("the AND machine", "no indexable term"),
        ("((machine)", "Missing closing"),
    ],
)
def test_invalid_queries_raise_useful_errors(retriever, query, fragment):
    with pytest.raises(BooleanQueryError) as exc:
        retriever.search(query)
    assert fragment.lower() in exc.value.message.lower()


def test_error_reports_position(retriever):
    with pytest.raises(BooleanQueryError) as exc:
        retriever.search("machine AND (learning")
    assert exc.value.position == 12


def test_excessive_nesting_rejected(retriever):
    with pytest.raises(BooleanQueryError, match="nested too deeply"):
        retriever.search("(" * 200 + "machine" + ")" * 200)
    with pytest.raises(BooleanQueryError, match="nested too deeply"):
        retriever.search("NOT " * 200 + "machine")


def test_unknown_terms(retriever):
    r = retriever.search("quantum")
    assert r.doc_ids == [] and r.unknown_terms == ["quantum"]
    assert retriever.search("NOT quantum").doc_ids == [1, 2, 3, 4, 5, 6]
    assert retriever.search("python OR quantum").doc_ids == [3, 4, 6]
    assert retriever.search("python AND quantum").doc_ids == []


def test_multi_term_operand_is_conjunction(small_index):
    # an operand that the preprocessor splits into two index terms matches documents containing both
    r = BooleanRetriever(small_index, lambda w: w.lower().split("."))
    assert r.search("python.programming").doc_ids == [3, 4]


def test_explanation_steps(retriever):
    r = retriever.search("machine AND NOT hardware")
    assert [(s.operation, s.result_size) for s in r.steps] == [
        ("LOOKUP", 2),  # machine -> [1, 2]
        ("LOOKUP", 1),  # hardware -> [2]
        ("NOT", 5),     # complement of [2] in 6 docs
        ("AND", 1),     # [1,2] & [1,3,4,5,6]
    ]
    assert r.steps[0].description == "postings('machine') = [1, 2] (df=2)"
    assert r.parsed_expression == "(machine AND (NOT hardware))"
    assert r.ast["type"] == "AND" and r.ast["right"]["type"] == "NOT"


def test_tokenizer_positions():
    toks = tokenize_query("a AND (b)")
    assert [(t.kind, t.pos) for t in toks] == [("TERM", 0), ("AND", 2), ("LPAREN", 6), ("TERM", 7), ("RPAREN", 8)]


def test_merge_primitives():
    assert intersect([1, 3, 5, 7], [3, 4, 5, 8]) == [3, 5]
    assert union([1, 3, 5], [2, 3, 6]) == [1, 2, 3, 5, 6]
    assert difference([1, 2, 3, 4, 5], [2, 4, 9]) == [1, 3, 5]
    assert intersect([], [1]) == [] and union([], []) == [] and difference([], [1]) == []


def test_incidence_matrix(small_index):
    m = incidence_matrix(small_index, ["machine", "python", "quantum"], [1, 2, 3, 4])
    assert m == [[1, 1, 0, 0], [0, 0, 1, 1], [0, 0, 0, 0]]
