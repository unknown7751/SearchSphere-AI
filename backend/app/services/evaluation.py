"""Run a retrieval mode for a query and score the ranking against relevance judgments."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from app.services import metrics
from app.services.advanced_retrieval import DEFAULT_PSEUDO_FEEDBACK_DOCS, AdvancedRetriever, RetrievalMode
from app.services.rocchio import DEFAULT_ALPHA, DEFAULT_BETA, DEFAULT_GAMMA


@dataclass
class RetrievalOptions:
    """How to retrieve for an evaluation (mirrors the request body of the evaluation API)."""

    mode: RetrievalMode = "tfidf"
    top_k: int = 10
    feedback_relevant: Sequence[int] = field(default_factory=tuple)
    feedback_non_relevant: Sequence[int] = field(default_factory=tuple)
    pseudo_feedback_docs: int = DEFAULT_PSEUDO_FEEDBACK_DOCS
    alpha: float = DEFAULT_ALPHA
    beta: float = DEFAULT_BETA
    gamma: float = DEFAULT_GAMMA


@dataclass
class QueryEvaluation:
    query: str
    options: RetrievalOptions
    ranked: list[int]                       # full ranked list of document IDs
    result: metrics.RankedEvaluation        # metrics at the requested cut-off


def evaluate_query(
    retriever: AdvancedRetriever, query: str, relevant: Sequence[int], options: RetrievalOptions
) -> QueryEvaluation:
    ranked = retriever.ranked_doc_ids(
        options.mode,
        query,
        feedback_relevant=options.feedback_relevant,
        feedback_non_relevant=options.feedback_non_relevant,
        pseudo_feedback_docs=options.pseudo_feedback_docs,
        alpha=options.alpha,
        beta=options.beta,
        gamma=options.gamma,
    )
    return QueryEvaluation(query, options, ranked, metrics.evaluate_ranking(ranked, relevant, options.top_k))


def format_map_calculation(average_precisions: Sequence[float]) -> str:
    """Human-readable MAP arithmetic, e.g. ``(0.8333 + 0.5000) / 2 = 0.6667``."""
    if not average_precisions:
        return "no queries"
    terms = " + ".join(f"{ap:.4f}" for ap in average_precisions)
    return f"({terms}) / {len(average_precisions)} = {metrics.mean_average_precision(average_precisions):.4f}"
