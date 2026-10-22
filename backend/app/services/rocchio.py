"""Rocchio relevance feedback in the TF-IDF vector space.

    q_m = alpha * q0  +  (beta / |Dr|) * sum(d in Dr)  -  (gamma / |Dnr|) * sum(d in Dnr)

Rocchio is *not* "adding the words of relevant documents to the query". The original
query, every relevant document and every non-relevant document are vectors in the same
TF-IDF space. The formula moves the query vector towards the centroid of the relevant
documents and away from the centroid of the non-relevant ones. The new vector is then
compared with every document by cosine similarity, which is what changes the ranking.

Conventions (all switchable, all reported back to the caller):

* ``normalize=True``  q0 and every document vector are scaled to unit length first (the
  textbook formulation), so a long document does not dominate the centroid and
  alpha/beta/gamma are comparable weights. ``normalize=False`` applies the raw TF-IDF
  vectors exactly as written in the formula.
* ``clip_negative=True`` negative components of q_m are set to 0 (a term cannot be
  "anti-wanted" by the cosine ranker). The unclipped vector is still returned.
* An empty set contributes nothing (no division by zero); zero vectors are legal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

import numpy as np

DEFAULT_ALPHA = 1.0
DEFAULT_BETA = 0.75
DEFAULT_GAMMA = 0.15

Vector = Mapping[str, float]


class RocchioError(ValueError):
    """Invalid Rocchio input (negative weights, a document in both feedback sets, ...)."""


def dedupe_ids(ids: Sequence[int] | None) -> list[int]:
    """Drop duplicate document IDs, keeping first-seen order."""
    return list(dict.fromkeys(ids or ()))


def validate_weights(alpha: float, beta: float, gamma: float) -> None:
    for name, value in (("alpha", alpha), ("beta", beta), ("gamma", gamma)):
        if not math.isfinite(value) or value < 0:
            raise RocchioError(f"{name} must be a finite number >= 0 (got {value!r})")


def validate_feedback_sets(relevant_ids: Sequence[int], non_relevant_ids: Sequence[int]) -> tuple[list[int], list[int]]:
    relevant, non_relevant = dedupe_ids(relevant_ids), dedupe_ids(non_relevant_ids)
    both = sorted(set(relevant) & set(non_relevant))
    if both:
        raise RocchioError(f"Documents cannot be both relevant and non-relevant: {both}")
    return relevant, non_relevant


def l2_normalize(vec: Vector) -> dict[str, float]:
    norm = math.sqrt(sum(w * w for w in vec.values()))
    return {t: w / norm for t, w in vec.items()} if norm > 0 else dict(vec)


def centroid_sum(vectors: Sequence[Vector], terms: list[str]) -> np.ndarray:
    """Sum of sparse vectors over a fixed term axis."""
    total = np.zeros(len(terms), dtype=float)
    for vec in vectors:
        total += np.array([vec.get(t, 0.0) for t in terms], dtype=float)
    return total


@dataclass
class RocchioResult:
    alpha: float
    beta: float
    gamma: float
    normalized: bool
    clip_negative: bool
    relevant_ids: list[int]
    non_relevant_ids: list[int]
    original_vector: dict[str, float]            # q0 as used in the formula (after optional normalisation)
    relevant_contribution: dict[str, float]      # (beta / |Dr|)  * sum of relevant vectors
    non_relevant_contribution: dict[str, float]  # (gamma / |Dnr|) * sum of non-relevant vectors (subtracted)
    unclipped_vector: dict[str, float]           # q_m before clipping negatives
    updated_vector: dict[str, float]             # q_m used for retrieval (non-zero components only)
    clipped_terms: list[str] = field(default_factory=list)

    @property
    def terms(self) -> list[str]:
        return sorted(set(self.original_vector) | set(self.relevant_contribution) | set(self.non_relevant_contribution))


def rocchio(
    original: Vector,
    relevant_vectors: Sequence[Vector],
    non_relevant_vectors: Sequence[Vector],
    *,
    alpha: float = DEFAULT_ALPHA,
    beta: float = DEFAULT_BETA,
    gamma: float = DEFAULT_GAMMA,
    normalize: bool = True,
    clip_negative: bool = True,
    relevant_ids: Sequence[int] = (),
    non_relevant_ids: Sequence[int] = (),
) -> RocchioResult:
    """Apply the Rocchio formula to sparse vectors (dict term -> weight)."""
    validate_weights(alpha, beta, gamma)
    prep = l2_normalize if normalize else dict
    q0 = prep(original)
    rel = [prep(v) for v in relevant_vectors]
    non = [prep(v) for v in non_relevant_vectors]

    terms = sorted(set(q0).union(*rel, *non))
    q_arr = np.array([q0.get(t, 0.0) for t in terms], dtype=float)
    rel_arr = (beta / len(rel)) * centroid_sum(rel, terms) if rel else np.zeros(len(terms))
    non_arr = (gamma / len(non)) * centroid_sum(non, terms) if non else np.zeros(len(terms))
    raw = alpha * q_arr + rel_arr - non_arr
    final = np.maximum(raw, 0.0) if clip_negative else raw

    def as_dict(arr: np.ndarray) -> dict[str, float]:
        return {t: float(v) for t, v in zip(terms, arr) if v != 0.0}

    return RocchioResult(
        alpha=alpha,
        beta=beta,
        gamma=gamma,
        normalized=normalize,
        clip_negative=clip_negative,
        relevant_ids=list(relevant_ids),
        non_relevant_ids=list(non_relevant_ids),
        original_vector=as_dict(q_arr),
        relevant_contribution=as_dict(rel_arr),
        non_relevant_contribution=as_dict(non_arr),
        unclipped_vector=as_dict(raw),
        updated_vector=as_dict(final),
        clipped_terms=[t for t, v in zip(terms, raw) if clip_negative and v < 0.0],
    )


def top_terms(vector: Vector, n: int, *, positive: bool = True) -> list[tuple[str, float]]:
    """Largest (``positive=True``) or most negative components, ties broken alphabetically."""
    items = [(t, w) for t, w in vector.items() if (w > 0 if positive else w < 0)]
    items.sort(key=lambda kv: (-kv[1] if positive else kv[1], kv[0]))
    return items[:n]
