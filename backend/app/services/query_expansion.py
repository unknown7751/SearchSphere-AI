"""Corpus-driven query expansion (pseudo-relevance feedback on terms).

Motivation: a short query such as "machine learning" misses documents that talk about the
same topic with different words (classification, training, ...). We look at what the
*best-ranked documents for the original query* talk about and add the terms they share.

Algorithm (deterministic, no LLM, no thesaurus - every added term is evidence from the corpus):

1. Rank the corpus with the original query (TF-IDF / cosine).
2. Take the top ``feedback_docs`` documents as the "pseudo-relevant" set ``F``.
3. Score every candidate term ``t`` that is not already in the query::

       score(t) = sum over d in F of  cos(q, d) * tfidf(t, d) / ||d||   /   sum over d in F of cos(q, d)

   i.e. the centroid of the length-normalised TF-IDF vectors of ``F``, where each document
   counts in proportion to how well it matched the query (so a weakly matching document
   such as "Java Virtual *Machine*" influences the expansion less than "Machine Learning").
4. Keep only terms that are supported by the corpus: document frequency >= ``min_df`` and
   present in at least ``min_support`` documents of ``F`` (one document is not evidence).
5. The ``max_terms`` best terms (ties broken alphabetically) are the *expanded terms*.
6. Expanded query vector = original query vector + ``expansion_weight * idf(t)`` for every
   expanded term (an added term counts as a fraction of a typed term).

Original Query -> Expanded Terms -> Final Expanded Query are reported separately.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from app.services.ranking import Ranker, RankingResult, TfidfModel

DEFAULT_FEEDBACK_DOCS = 5
DEFAULT_MAX_TERMS = 5
DEFAULT_MIN_DF = 2
DEFAULT_MIN_SUPPORT = 2
DEFAULT_EXPANSION_WEIGHT = 0.5
CANDIDATES_REPORTED = 20


@dataclass
class ExpansionCandidate:
    term: str            # index term (stem)
    display: str         # readable word used in the final query text
    score: float
    support: int         # number of feedback documents containing the term
    df: int
    idf: float
    selected: bool = False


@dataclass
class ExpansionResult:
    original_terms: list[str]
    feedback_doc_ids: list[int]
    candidates: list[ExpansionCandidate]       # best candidates incl. rejected-by-limit ones
    expanded_terms: list[ExpansionCandidate]   # the selected ones
    expansion_weight: float
    original_vector: dict[str, float]
    expanded_vector: dict[str, float]
    reason: str | None = None                  # set when nothing could be expanded
    initial_ranking: RankingResult | None = field(default=None, repr=False)

    def final_query_text(self, original_query: str) -> str:
        return " ".join([original_query.strip(), *[c.display for c in self.expanded_terms]]).strip()


class QueryExpander:
    def __init__(self, model: TfidfModel, ranker: Ranker):
        self.model = model
        self.ranker = ranker

    def expand(
        self,
        query_terms: list[str],
        *,
        feedback_docs: int = DEFAULT_FEEDBACK_DOCS,
        max_terms: int = DEFAULT_MAX_TERMS,
        min_df: int = DEFAULT_MIN_DF,
        min_support: int = DEFAULT_MIN_SUPPORT,
        expansion_weight: float = DEFAULT_EXPANSION_WEIGHT,
    ) -> ExpansionResult:
        index = self.model.index
        original_vector, _ = self.model.query_vector(query_terms)
        base = self.ranker.rank_vector(original_vector)
        result = ExpansionResult(
            original_terms=list(dict.fromkeys(query_terms)),
            feedback_doc_ids=[],
            candidates=[],
            expanded_terms=[],
            expansion_weight=expansion_weight,
            original_vector=original_vector,
            expanded_vector=dict(original_vector),
            initial_ranking=base,
        )
        top = base.ranked[:feedback_docs]
        feedback = [s.doc_id for s in top]
        result.feedback_doc_ids = feedback
        if not feedback:
            result.reason = "No document matches the query, so there is nothing to learn expansion terms from."
            return result

        totals: Counter[str] = Counter()
        support: Counter[str] = Counter()
        total_match = sum(s.score for s in top)
        for scored in top:
            vec = self.model.document_vector(scored.doc_id)
            norm = math.sqrt(sum(w * w for w in vec.values()))
            if norm == 0:
                continue
            for term, weight in vec.items():
                totals[term] += scored.score * weight / norm
                support[term] += 1

        needed_support = min(min_support, len(feedback))
        candidates = [
            ExpansionCandidate(t, index.display_form(t), totals[t] / total_match, support[t], index.df(t), self.model.idf(t))
            for t in totals
            if t not in original_vector and index.df(t) >= min_df and support[t] >= needed_support
        ]
        candidates.sort(key=lambda c: (-round(c.score, 12), c.term))
        for cand in candidates[:max_terms]:
            cand.selected = True
        result.candidates = candidates[:CANDIDATES_REPORTED]
        result.expanded_terms = candidates[:max_terms]
        for cand in result.expanded_terms:
            result.expanded_vector[cand.term] = expansion_weight * cand.idf
        if not result.expanded_terms:
            result.reason = "No candidate term was supported by enough top-ranked documents."
        return result
