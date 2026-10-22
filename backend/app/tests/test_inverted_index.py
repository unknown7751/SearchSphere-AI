import pytest

from app.services.inverted_index import DuplicateDocumentError, InvertedIndex, Posting
from app.tests.conftest import SMALL_CORPUS, build_index


def test_postings_are_sorted_and_unique(small_index):
    for term in small_index.vocabulary():
        ids = small_index.doc_ids(term)
        assert ids == sorted(set(ids))
    assert small_index.doc_ids("python") == [3, 4, 6]


def test_postings_sorted_even_when_documents_added_out_of_order():
    index = InvertedIndex()
    for doc_id in (9, 2, 5):
        index.add_document(doc_id, ["alpha"])
    assert index.doc_ids("alpha") == [2, 5, 9]


def test_term_frequency(small_index):
    assert small_index.tf("machine", 1) == 2
    assert small_index.tf("machine", 2) == 1
    assert small_index.tf("machine", 3) == 0
    assert small_index.postings("machine") == [Posting(1, 2), Posting(2, 1)]


def test_document_frequency(small_index):
    assert small_index.df("python") == 3
    assert small_index.df("machine") == 2
    assert small_index.df("security") == 1
    assert small_index.df("nonexistent") == 0


def test_vocabulary_is_alphabetically_sorted(small_index):
    assert small_index.vocabulary() == ["hardware", "java", "learning", "machine", "programming", "python", "security"]


def test_unknown_term_returns_empty(small_index):
    assert small_index.doc_ids("quantum") == []
    assert small_index.postings("quantum") == []


def test_add_document_updates_everything(small_index):
    small_index.add_document(7, ["quantum", "python", "python"])
    assert small_index.num_docs == 7
    assert small_index.doc_ids("python") == [3, 4, 6, 7]
    assert small_index.tf("python", 7) == 2
    assert small_index.df("python") == 4
    assert small_index.df("quantum") == 1
    assert "quantum" in small_index.vocabulary()
    assert small_index.vocabulary() == sorted(small_index.vocabulary())
    assert small_index.check_consistency() == []


def test_add_duplicate_document_rejected(small_index):
    with pytest.raises(DuplicateDocumentError):
        small_index.add_document(1, ["x"])
    assert small_index.check_consistency() == []


def test_delete_document_updates_everything(small_index):
    assert small_index.remove_document(5) is True  # only doc containing 'security'
    assert "security" not in small_index.vocabulary()
    assert small_index.df("security") == 0
    assert small_index.num_docs == 5

    assert small_index.remove_document(3) is True
    assert small_index.doc_ids("python") == [4, 6]
    assert small_index.doc_ids("programming") == [4]
    assert not small_index.has_document(3)
    assert small_index.check_consistency() == []


def test_delete_missing_document_is_noop(small_index):
    assert small_index.remove_document(999) is False
    assert small_index.num_docs == 6


def test_delete_then_readd_restores_identical_index():
    index = build_index()
    index.remove_document(4)
    index.add_document(4, SMALL_CORPUS[4])
    fresh = build_index()
    assert index.vocabulary() == fresh.vocabulary()
    for term in fresh.vocabulary():
        assert index.postings(term) == fresh.postings(term)


def test_consistency_check_passes_on_valid_index(small_index):
    assert small_index.check_consistency() == []


def test_consistency_check_detects_corruption(small_index):
    small_index._postings["python"][3] = 99  # postings now disagree with the forward index
    assert any("python" in p for p in small_index.check_consistency())


def test_consistency_check_detects_dangling_postings(small_index):
    small_index._postings["ghost"] = {42: 1}
    problems = small_index.check_consistency()
    assert any("unknown doc 42" in p for p in problems)


def test_empty_document_is_counted_but_has_no_postings(small_index):
    small_index.add_document(8, [])
    assert small_index.num_docs == 7
    assert 8 in small_index.all_doc_ids()
    assert small_index.check_consistency() == []


def test_inspect_output(small_index):
    assert small_index.inspect("machine") == {
        "term": "machine",
        "document_frequency": 2,
        "postings": [{"doc_id": 1, "tf": 2}, {"doc_id": 2, "tf": 1}],
    }


def test_stats(small_index):
    s = small_index.stats()
    assert s["num_documents"] == 6
    assert s["vocabulary_size"] == 7
    assert s["total_tokens"] == 13
    assert s["total_postings"] == 12  # distinct (term, doc) pairs: 2+2+2+3+1+2
    assert s["average_document_length"] == pytest.approx(13 / 6)


def test_surface_terms_must_align_and_not_conflict():
    index = InvertedIndex()
    index.add_document(1, ["comput"], ["computer"])
    with pytest.raises(ValueError):
        index.add_document(2, ["comput", "x"], ["computer"])
    with pytest.raises(ValueError):
        index.add_document(2, ["other"], ["computer"])  # 'computer' already maps to 'comput'
    assert index.num_docs == 1
    assert index.check_consistency() == []


def test_surface_dictionary_tracks_removal():
    index = InvertedIndex()
    index.add_document(1, ["comput", "comput"], ["computer", "computing"])
    index.add_document(2, ["comput"], ["computer"])
    assert index.surface_vocabulary() == ["computer", "computing"]
    index.remove_document(1)
    assert index.surface_vocabulary() == ["computer"]
    assert index.surface_doc_ids("computer") == [2]
    assert index.check_consistency() == []
