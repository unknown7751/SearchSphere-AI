"""Evaluation metrics, checked against hand calculations."""
import pytest

from app.services import metrics as m

# Ranking D1..D5 (ids 1..5); relevant {1, 3, 5}
RANKED = [1, 2, 3, 4, 5]
RELEVANT = [1, 3, 5]


def test_precision_recall_f1_partial():
    retrieved = [1, 2, 3, 4]  # 2 relevant of 4 retrieved, 3 relevant in total
    assert m.precision(retrieved, RELEVANT) == pytest.approx(2 / 4)
    assert m.recall(retrieved, RELEVANT) == pytest.approx(2 / 3)
    p, r = 2 / 4, 2 / 3
    assert m.f1_score(p, r) == pytest.approx(2 * p * r / (p + r))


def test_perfect_retrieval():
    assert m.precision([1, 3, 5], RELEVANT) == 1.0
    assert m.recall([1, 3, 5], RELEVANT) == 1.0
    assert m.f1_score(1.0, 1.0) == 1.0
    assert m.average_precision([1, 3, 5], RELEVANT) == 1.0


def test_zero_retrieval_and_zero_overlap():
    assert m.precision([], RELEVANT) == 0.0
    assert m.recall([], RELEVANT) == 0.0
    assert m.precision([2, 4], RELEVANT) == 0.0
    assert m.recall([2, 4], RELEVANT) == 0.0
    assert m.f1_score(0.0, 0.0) == 0.0
    assert m.average_precision([2, 4], RELEVANT) == 0.0


def test_no_relevant_documents_never_divides_by_zero():
    assert m.recall(RANKED, []) == 0.0
    assert m.recall_at_k(RANKED, [], 3) == 0.0
    assert m.average_precision(RANKED, []) == 0.0
    assert m.precision(RANKED, []) == 0.0


def test_all_documents_relevant():
    assert m.precision(RANKED, RANKED) == 1.0
    assert m.recall(RANKED, RANKED) == 1.0
    assert m.precision_at_k(RANKED, RANKED, 3) == 1.0


def test_precision_at_k_values():
    assert m.precision_at_k(RANKED, RELEVANT, 1) == 1.0          # D1 relevant
    assert m.precision_at_k(RANKED, RELEVANT, 2) == 0.5
    assert m.precision_at_k(RANKED, RELEVANT, 3) == pytest.approx(2 / 3)
    assert m.precision_at_k(RANKED, RELEVANT, 5) == pytest.approx(3 / 5)


def test_k_larger_than_result_count_divides_by_k():
    # 5 results, k = 10: three relevant in the top 10 slots -> 3/10 (missing slots count against precision)
    assert m.precision_at_k(RANKED, RELEVANT, 10) == pytest.approx(0.3)
    assert m.recall_at_k(RANKED, RELEVANT, 10) == 1.0


def test_recall_at_k_values():
    assert m.recall_at_k(RANKED, RELEVANT, 1) == pytest.approx(1 / 3)
    assert m.recall_at_k(RANKED, RELEVANT, 3) == pytest.approx(2 / 3)
    assert m.recall_at_k(RANKED, RELEVANT, 5) == 1.0


@pytest.mark.parametrize("k", [0, -1, -100])
def test_invalid_k_rejected(k):
    with pytest.raises(m.MetricError):
        m.precision_at_k(RANKED, RELEVANT, k)
    with pytest.raises(m.MetricError):
        m.recall_at_k(RANKED, RELEVANT, k)
    with pytest.raises(m.MetricError):
        m.evaluate_ranking(RANKED, RELEVANT, k)


def test_average_precision_worked_example():
    """Retrieved D1..D5, relevant D1, D3, D5: AP = (P@1 + P@3 + P@5) / 3 = (1 + 2/3 + 3/5) / 3."""
    result = m.average_precision_steps(RANKED, RELEVANT)
    assert [(s.rank, s.doc_id) for s in result.steps] == [(1, 1), (3, 3), (5, 5)]
    assert [s.precision_at_rank for s in result.steps] == pytest.approx([1.0, 2 / 3, 3 / 5])
    assert result.average_precision == pytest.approx((1 + 2 / 3 + 3 / 5) / 3)
    assert m.average_precision(RANKED, RELEVANT) == pytest.approx(0.7555555555)


def test_average_precision_penalises_unretrieved_relevant_documents():
    # only one of two relevant documents is retrieved, at rank 1 -> (1/1) / 2
    assert m.average_precision([7, 8], [7, 99]) == pytest.approx(0.5)


def test_average_precision_prefers_earlier_relevant_documents():
    assert m.average_precision([1, 2, 3], [1]) > m.average_precision([2, 3, 1], [1])


def test_duplicate_ids_in_ranking_or_judgments_are_ignored():
    assert m.precision([1, 1, 2], [1]) == 0.5
    assert m.recall([1, 2], [1, 1, 1]) == 1.0
    assert m.average_precision([1, 1, 2], [1, 1]) == 1.0


def test_mean_average_precision_known_values():
    q1 = m.average_precision([1, 2, 3, 4, 5], [1, 3, 5])   # 0.7556
    q2 = m.average_precision([9, 8, 7], [8])               # 1/2
    q3 = m.average_precision([1, 2], [3])                  # 0
    assert m.mean_average_precision([q1, q2, q3]) == pytest.approx((q1 + 0.5 + 0.0) / 3)
    assert m.mean_average_precision([q1, q2]) == pytest.approx((0.75555555555 + 0.5) / 2)


def test_map_of_no_queries_is_zero():
    assert m.mean_average_precision([]) == 0.0


def test_evaluate_ranking_bundles_everything():
    ev = m.evaluate_ranking(RANKED, RELEVANT, k=3)
    assert ev.retrieved_at_k == [1, 2, 3]
    assert ev.relevant_retrieved == [1, 3]
    assert ev.precision == pytest.approx(2 / 3)
    assert ev.recall == pytest.approx(2 / 3)
    assert ev.f1 == pytest.approx(2 / 3)
    assert ev.precision_at_k == pytest.approx(2 / 3)
    assert ev.recall_at_k == pytest.approx(2 / 3)
    assert ev.precision_at_each_rank == pytest.approx([1.0, 0.5, 2 / 3])
    # AP runs over the whole ranking, not just the cut-off
    assert ev.average_precision == pytest.approx((1 + 2 / 3 + 3 / 5) / 3)


def test_evaluate_ranking_k_one_and_short_ranking():
    ev = m.evaluate_ranking([4, 1], [1], k=1)
    assert ev.precision == 0.0 and ev.recall == 0.0 and ev.f1 == 0.0
    assert ev.average_precision == pytest.approx(0.5)
    ev = m.evaluate_ranking([1], [1], k=5)
    assert ev.precision == 1.0 and ev.precision_at_k == pytest.approx(0.2)
