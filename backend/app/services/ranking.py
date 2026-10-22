"""Manual TF-IDF weighting and cosine-similarity ranking (no sklearn).

Conventions (documented so they can be explained in a viva):

* ``tf(t, d)``   raw count of term ``t`` in document ``d`` (no log scaling, no
                 length normalisation - cosine normalisation handles length).
* ``df(t)``      number of indexed documents containing ``t``.
* ``idf(t)``     ``ln((N + 1) / (df(t) + 1)) + 1`` with ``N`` = number of indexed docs
                 (smoothed; always >= 1, defined even when df = 0).
* ``tfidf(t,d)`` ``tf(t, d) * idf(t)``.
* Query vector   raw query-term counts times the same idf. Query terms that are not in
                 the vocabulary (df = 0) are dropped from the vector and reported as
                 unknown; they could not contribute to any dot product anyway.
* ``cosine(q,d)``  ``dot(q, d) / (||q|| * ||d||)``; 0.0 if either vector is zero.
* Ranking        score descending, ties broken by ascending document ID.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Mapping

import numpy as np

from app.services.inverted_index import InvertedIndex

SCORE_PRECISION = 12  # scores equal up to float noise are treated as ties


def compute_idf(num_docs: int, df: int) -> float:
    return float(np.log((num_docs + 1) / (df + 1)) + 1.0)


@dataclass
class CosineBreakdown:
    dot: float
    query_norm: float
    doc_norm: float
    score: float


def cosine_similarity(q: Mapping[str, float], d: Mapping[str, float]) -> CosineBreakdown:
    """Cosine of two sparse vectors (dicts term -> weight), computed with NumPy."""
    if not q or not d:
        return CosineBreakdown(0.0, 0.0, 0.0, 0.0)
    terms = sorted(set(q) | set(d))
    qa = np.array([q.get(t, 0.0) for t in terms], dtype=float)
    da = np.array([d.get(t, 0.0) for t in terms], dtype=float)
    dot = float(np.dot(qa, da))
    qn, dn = float(np.linalg.norm(qa)), float(np.linalg.norm(da))
    score = dot / (qn * dn) if qn > 0 and dn > 0 else 0.0
    return CosineBreakdown(dot, qn, dn, min(1.0, max(0.0, score)))


@dataclass
class ScoredDocument:
    doc_id: int
    score: float
    dot: float
    query_norm: float
    doc_norm: float
    term_contributions: dict[str, float] = field(default_factory=dict)  # q_w * d_w per shared term


@dataclass
class RankingResult:
    query_vector: dict[str, float]
    unknown_terms: list[str]
    ranked: list[ScoredDocument]


class TfidfModel:
    """TF-IDF statistics and vectors computed on demand from an :class:`InvertedIndex`."""

    def __init__(self, index: InvertedIndex):
        self.index = index
        self._cache_version = -1
        self._doc_vectors: dict[int, dict[str, float]] = {}

    @property
    def num_docs(self) -> int:
        return self.index.num_docs

    def tf(self, term: str, doc_id: int) -> int:
        return self.index.tf(term, doc_id)

    def df(self, term: str) -> int:
        return self.index.df(term)

    def idf(self, term: str) -> float:
        return compute_idf(self.num_docs, self.df(term))

    def tfidf(self, term: str, doc_id: int) -> float:
        return self.tf(term, doc_id) * self.idf(term)

    def document_vector(self, doc_id: int) -> dict[str, float]:
        if self._cache_version != self.index.version:  # idf depends on N and df, so any change invalidates
            self._doc_vectors.clear()
            self._cache_version = self.index.version
        vec = self._doc_vectors.get(doc_id)
        if vec is None:
            vec = {t: tf * self.idf(t) for t, tf in self.index.term_freqs(doc_id).items()}
            self._doc_vectors[doc_id] = vec
        return vec

    def query_vector(self, terms: Iterable[str]) -> tuple[dict[str, float], list[str]]:
        counts = Counter(terms)
        vec, unknown = {}, []
        for t in sorted(counts):
            if self.df(t) == 0:
                unknown.append(t)
            else:
                vec[t] = counts[t] * self.idf(t)
        return vec, unknown

    def top_terms(self, doc_id: int, n: int = 10) -> list[dict]:
        """Highest-weighted terms of a document with all four quantities exposed."""
        vec = self.document_vector(doc_id)
        ranked = sorted(vec.items(), key=lambda kv: (-round(kv[1], SCORE_PRECISION), kv[0]))[:n]
        return [
            {"term": t, "tf": self.tf(t, doc_id), "df": self.df(t), "idf": self.idf(t), "tfidf": w}
            for t, w in ranked
        ]


class Ranker:
    def __init__(self, model: TfidfModel):
        self.model = model

    def score_document(self, qvec: Mapping[str, float], doc_id: int) -> ScoredDocument:
        dvec = self.model.document_vector(doc_id)
        cos = cosine_similarity(qvec, dvec)
        contributions = {t: qvec[t] * dvec[t] for t in sorted(qvec) if t in dvec}
        return ScoredDocument(doc_id, cos.score, cos.dot, cos.query_norm, cos.doc_norm, contributions)

    def rank(self, query_terms: Iterable[str], candidate_ids: Iterable[int] | None = None) -> RankingResult:
        qvec, unknown = self.model.query_vector(query_terms)
        if candidate_ids is None:  # every document sharing at least one query term
            cands: set[int] = set()
            for t in qvec:
                cands.update(self.model.index.doc_ids(t))
        else:
            cands = {d for d in candidate_ids if self.model.index.has_document(d)}
        scored = [self.score_document(qvec, d) for d in cands]
        if candidate_ids is None:
            scored = [s for s in scored if s.score > 0]
        scored.sort(key=lambda s: (-round(s.score, SCORE_PRECISION), s.doc_id))
        return RankingResult(qvec, unknown, scored)
