"""Manual IR evaluation metrics (no sklearn).

Every function works on plain Python lists of document IDs, so each formula can be
checked by hand. Division by zero is always defined as 0.0.

* ``precision``        relevant retrieved / retrieved
* ``recall``           relevant retrieved / total relevant
* ``f1``               2PR / (P + R)
* ``precision_at_k``   relevant in top k / k           (k is the *requested* cut-off, so a
                       ranking shorter than k is penalised for its missing slots)
* ``recall_at_k``      relevant in top k / total relevant
* ``average_precision``  mean of P@rank taken at the rank of every relevant document;
                       relevant documents that are never retrieved contribute 0 because
                       the sum is divided by the *total* number of relevant documents
* ``mean_average_precision``  mean of AP over several queries
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


class MetricError(ValueError):
    """Invalid metric input (for example k <= 0)."""


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _unique(ids: Sequence[int]) -> list[int]:
    return list(dict.fromkeys(ids))


def count_relevant_retrieved(retrieved: Sequence[int], relevant: Sequence[int]) -> int:
    relevant_set = set(relevant)
    return sum(1 for doc_id in _unique(retrieved) if doc_id in relevant_set)


def precision(retrieved: Sequence[int], relevant: Sequence[int]) -> float:
    retrieved = _unique(retrieved)
    return _safe_divide(count_relevant_retrieved(retrieved, relevant), len(retrieved))


def recall(retrieved: Sequence[int], relevant: Sequence[int]) -> float:
    return _safe_divide(count_relevant_retrieved(retrieved, relevant), len(set(relevant)))


def f1_score(precision_value: float, recall_value: float) -> float:
    return _safe_divide(2 * precision_value * recall_value, precision_value + recall_value)


def _check_k(k: int) -> None:
    if k <= 0:
        raise MetricError("k must be a positive integer")


def precision_at_k(ranked: Sequence[int], relevant: Sequence[int], k: int) -> float:
    _check_k(k)
    return _safe_divide(count_relevant_retrieved(_unique(ranked)[:k], relevant), k)


def recall_at_k(ranked: Sequence[int], relevant: Sequence[int], k: int) -> float:
    _check_k(k)
    return _safe_divide(count_relevant_retrieved(_unique(ranked)[:k], relevant), len(set(relevant)))


@dataclass
class APStep:
    """One relevant document found in the ranking and the precision at its rank."""

    rank: int
    doc_id: int
    relevant_so_far: int
    precision_at_rank: float


@dataclass
class AveragePrecisionResult:
    average_precision: float
    total_relevant: int
    steps: list[APStep] = field(default_factory=list)


def average_precision_steps(ranked: Sequence[int], relevant: Sequence[int]) -> AveragePrecisionResult:
    """AP with the P@k value at every relevant rank exposed (for viva demonstrations)."""
    relevant_set = set(relevant)
    steps: list[APStep] = []
    found = 0
    for rank, doc_id in enumerate(_unique(ranked), start=1):
        if doc_id in relevant_set:
            found += 1
            steps.append(APStep(rank, doc_id, found, found / rank))
    total = len(relevant_set)
    return AveragePrecisionResult(_safe_divide(sum(s.precision_at_rank for s in steps), total), total, steps)


def average_precision(ranked: Sequence[int], relevant: Sequence[int]) -> float:
    return average_precision_steps(ranked, relevant).average_precision


def mean_average_precision(average_precisions: Sequence[float]) -> float:
    return _safe_divide(sum(average_precisions), len(average_precisions))


@dataclass
class RankedEvaluation:
    """All metrics for one ranked list, with the intermediate counts."""

    k: int
    retrieved_at_k: list[int]
    relevant: list[int]
    relevant_retrieved: list[int]
    precision: float
    recall: float
    f1: float
    precision_at_k: float
    recall_at_k: float
    average_precision: float
    ap_steps: list[APStep]
    precision_at_each_rank: list[float]  # P@1 .. P@k over the actual retrieved cut-off


def evaluate_ranking(ranked: Sequence[int], relevant: Sequence[int], k: int) -> RankedEvaluation:
    """Evaluate ``ranked`` against ``relevant``.

    The *retrieved set* used by precision / recall / F1 is the top ``k`` documents; AP is
    computed over the whole ranked list.
    """
    _check_k(k)
    ranked = _unique(ranked)
    relevant = sorted(set(relevant))
    top_k = ranked[:k]
    relevant_set = set(relevant)
    relevant_retrieved = [d for d in top_k if d in relevant_set]
    p, r = precision(top_k, relevant), recall(top_k, relevant)
    ap = average_precision_steps(ranked, relevant)
    running, per_rank = 0, []
    for rank, doc_id in enumerate(top_k, start=1):
        running += doc_id in relevant_set
        per_rank.append(running / rank)
    return RankedEvaluation(
        k=k,
        retrieved_at_k=top_k,
        relevant=relevant,
        relevant_retrieved=relevant_retrieved,
        precision=p,
        recall=r,
        f1=f1_score(p, r),
        precision_at_k=precision_at_k(ranked, relevant, k),
        recall_at_k=recall_at_k(ranked, relevant, k),
        average_precision=ap.average_precision,
        ap_steps=ap.steps,
        precision_at_each_rank=per_rank,
    )
