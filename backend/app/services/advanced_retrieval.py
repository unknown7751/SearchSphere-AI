"""Retrieval modes built on the TF-IDF model: expanded query and Rocchio feedback.

Both modes end the same way as plain TF-IDF search - a query *vector* is compared with
every candidate document by cosine similarity (``Ranker.rank_vector``) - so the modified
query genuinely changes the ranking instead of only being displayed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from app.services import rocchio as rocchio_math
from app.services.query_expansion import (
    DEFAULT_EXPANSION_WEIGHT,
    DEFAULT_FEEDBACK_DOCS,
    DEFAULT_MAX_TERMS,
    ExpansionResult,
    QueryExpander,
)
from app.services.ranking import Ranker, RankingResult, TfidfModel
from app.services.rocchio import DEFAULT_ALPHA, DEFAULT_BETA, DEFAULT_GAMMA, RocchioResult

RetrievalMode = Literal["tfidf", "expanded", "rocchio", "boolean"]
DEFAULT_PSEUDO_FEEDBACK_DOCS = 3


class UnknownDocumentsError(LookupError):
    """Feedback referenced document IDs that are not in the index."""

    def __init__(self, missing: list[int]):
        super().__init__(f"Documents not found in the index: {missing}")
        self.missing = missing


@dataclass
class RocchioSearch:
    rocchio: RocchioResult
    original_vector: dict[str, float]
    unknown_terms: list[str]
    baseline: RankingResult   # ranking by the original query vector
    ranking: RankingResult    # ranking by the Rocchio-modified vector
    pseudo_feedback: bool     # True when relevant documents were taken from the baseline top-k


@dataclass
class ExpandedSearch:
    expansion: ExpansionResult
    baseline: RankingResult
    ranking: RankingResult


class AdvancedRetriever:
    def __init__(self, model: TfidfModel, ranker: Ranker, preprocessor, boolean):
        self.model = model
        self.ranker = ranker
        self.preprocessor = preprocessor
        self.boolean = boolean
        self.expander = QueryExpander(model, ranker)

    # -------------------------------------------------------------- expansion
    def expanded_search(
        self,
        query: str,
        *,
        feedback_docs: int = DEFAULT_FEEDBACK_DOCS,
        max_terms: int = DEFAULT_MAX_TERMS,
        expansion_weight: float = DEFAULT_EXPANSION_WEIGHT,
    ) -> ExpandedSearch:
        terms = self.preprocessor.index_terms(query)
        expansion = self.expander.expand(
            terms, feedback_docs=feedback_docs, max_terms=max_terms, expansion_weight=expansion_weight
        )
        baseline = expansion.initial_ranking or self.ranker.rank(terms)
        ranking = self.ranker.rank_vector(expansion.expanded_vector)
        return ExpandedSearch(expansion, baseline, ranking)

    # -------------------------------------------------------------- Rocchio
    def _require_indexed(self, ids: Sequence[int]) -> None:
        missing = [i for i in ids if not self.model.index.has_document(i)]
        if missing:
            raise UnknownDocumentsError(missing)

    def rocchio_search(
        self,
        query: str,
        relevant_ids: Sequence[int] | None = None,
        non_relevant_ids: Sequence[int] | None = None,
        *,
        alpha: float = DEFAULT_ALPHA,
        beta: float = DEFAULT_BETA,
        gamma: float = DEFAULT_GAMMA,
        normalize: bool = True,
        pseudo_feedback_docs: int = 0,
    ) -> RocchioSearch:
        """Modify the query vector with Rocchio and rank with it.

        ``pseudo_feedback_docs > 0`` and no explicit relevant IDs: the top-k documents of
        the baseline ranking are assumed relevant (pseudo-relevance feedback), which needs
        no human judgments and so cannot leak evaluation labels.
        """
        relevant, non_relevant = rocchio_math.validate_feedback_sets(relevant_ids or (), non_relevant_ids or ())
        rocchio_math.validate_weights(alpha, beta, gamma)
        self._require_indexed(relevant + non_relevant)

        terms = self.preprocessor.index_terms(query)
        original_vector, unknown = self.model.query_vector(terms)
        baseline = self.ranker.rank_vector(original_vector, unknown_terms=unknown)

        pseudo = False
        if not relevant and pseudo_feedback_docs > 0:
            excluded = set(non_relevant)
            relevant = [s.doc_id for s in baseline.ranked if s.doc_id not in excluded][:pseudo_feedback_docs]
            pseudo = bool(relevant)

        result = rocchio_math.rocchio(
            original_vector,
            [self.model.document_vector(d) for d in relevant],
            [self.model.document_vector(d) for d in non_relevant],
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            normalize=normalize,
            relevant_ids=relevant,
            non_relevant_ids=non_relevant,
        )
        ranking = self.ranker.rank_vector(result.updated_vector, unknown_terms=unknown)
        return RocchioSearch(result, original_vector, unknown, baseline, ranking, pseudo)

    # -------------------------------------------------------------- uniform interface for evaluation
    def ranked_doc_ids(
        self,
        mode: RetrievalMode,
        query: str,
        *,
        feedback_relevant: Sequence[int] | None = None,
        feedback_non_relevant: Sequence[int] | None = None,
        pseudo_feedback_docs: int = DEFAULT_PSEUDO_FEEDBACK_DOCS,
        alpha: float = DEFAULT_ALPHA,
        beta: float = DEFAULT_BETA,
        gamma: float = DEFAULT_GAMMA,
        feedback_docs: int = DEFAULT_FEEDBACK_DOCS,
        max_terms: int = DEFAULT_MAX_TERMS,
    ) -> list[int]:
        """Document IDs in ranked order for any retrieval mode (Boolean results are in ID order)."""
        if mode == "boolean":
            return self.boolean.search(query).doc_ids
        if mode == "expanded":
            return [s.doc_id for s in self.expanded_search(query, feedback_docs=feedback_docs, max_terms=max_terms).ranking.ranked]
        if mode == "rocchio":
            search = self.rocchio_search(
                query,
                feedback_relevant,
                feedback_non_relevant,
                alpha=alpha,
                beta=beta,
                gamma=gamma,
                pseudo_feedback_docs=pseudo_feedback_docs,
            )
            return [s.doc_id for s in search.ranking.ranked]
        return [s.doc_id for s in self.ranker.rank(self.preprocessor.index_terms(query)).ranked]

