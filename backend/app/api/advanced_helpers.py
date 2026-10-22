"""Presentation helpers for the Phase 2 endpoints (expansion / Rocchio payloads).

The mathematics lives in ``app.services``; these functions only turn service results into
JSON-friendly dictionaries, truncating vectors so responses stay small.
"""
from __future__ import annotations

import sqlite3

from app.core.errors import AppError
from app.database import repository as repo
from app.services import rocchio as rocchio_math
from app.services.advanced_retrieval import RocchioSearch, UnknownDocumentsError
from app.services.query_expansion import ExpansionResult
from app.services.ranking import RankingResult
from app.services.rocchio import RocchioError
from app.services.search_engine import SearchEngine

ROCCHIO_FORMULA = "q_m = alpha * q0 + (beta / |Dr|) * sum(d in Dr) d - (gamma / |Dnr|) * sum(d in Dnr) d"
SUMMARY_TERMS = 10


def run_rocchio(engine: SearchEngine, query: str, body) -> RocchioSearch:
    """Run Rocchio search for any request carrying the Rocchio fields, mapping errors to HTTP errors."""
    try:
        return engine.advanced.rocchio_search(
            query,
            body.relevant_doc_ids,
            body.non_relevant_doc_ids,
            alpha=body.alpha,
            beta=body.beta,
            gamma=body.gamma,
            normalize=body.normalize,
            pseudo_feedback_docs=body.pseudo_feedback_docs,
        )
    except UnknownDocumentsError as exc:
        raise AppError(404, "document_not_found", str(exc), {"missing": exc.missing}) from exc
    except RocchioError as exc:
        raise AppError(400, "invalid_rocchio_input", str(exc)) from exc


def top_vector(vector: dict[str, float], n: int) -> dict[str, float]:
    """The n largest-magnitude components (ties alphabetical)."""
    items = sorted(vector.items(), key=lambda kv: (-abs(kv[1]), kv[0]))[:n]
    return dict(items)


# ------------------------------------------------------------------ query expansion
def expansion_summary(original_query: str, expansion: ExpansionResult) -> dict:
    return {
        "original_query": original_query,
        "original_terms": expansion.original_terms,
        "feedback_doc_ids": expansion.feedback_doc_ids,
        "expanded_terms": [_candidate(c) for c in expansion.expanded_terms],
        "final_expanded_query": expansion.final_query_text(original_query),
        "expansion_weight": expansion.expansion_weight,
        "expanded_query_vector": expansion.expanded_vector,
        "message": expansion.reason,
    }


def _candidate(c) -> dict:
    return {
        "term": c.term,
        "display": c.display,
        "score": c.score,
        "support": c.support,
        "document_frequency": c.df,
        "idf": c.idf,
        "selected": c.selected,
    }


def ranking_rows(
    conn: sqlite3.Connection, ranking: RankingResult, top_k: int, baseline: RankingResult | None = None
) -> list[dict]:
    """Top-k ranking with titles and (optionally) rank movement relative to a baseline ranking."""
    shown = ranking.ranked[:top_k]
    docs = repo.get_documents(conn, [s.doc_id for s in shown])
    base_rank = {s.doc_id: i for i, s in enumerate(baseline.ranked, start=1)} if baseline else {}
    rows = []
    for rank, s in enumerate(shown, start=1):
        row = {"rank": rank, "doc_id": s.doc_id, "title": docs[s.doc_id].title, "score": s.score}
        if baseline is not None:
            before = base_rank.get(s.doc_id)
            row["baseline_rank"] = before
            row["rank_change"] = before - rank if before is not None else None  # positive = moved up
        rows.append(row)
    return rows


def expansion_workbench(engine: SearchEngine, conn: sqlite3.Connection, query: str, search, top_k: int) -> dict:
    analysis = engine.preprocessor.analyze(query)
    summary = expansion_summary(query, search.expansion)
    feedback_docs = repo.get_documents(conn, search.expansion.feedback_doc_ids)
    return {
        "input": {"query": query},
        "preprocessing": {
            "normalized": analysis.normalized,
            "tokens": analysis.tokens,
            "stop_words_removed": analysis.stop_words_removed,
            "index_terms": analysis.index_terms,
        },
        "method": (
            "Rank with the original query, take the top documents, score each other term by the centroid of their "
            "length-normalised TF-IDF vectors, keep terms present in >= 2 of those documents (and df >= 2)."
        ),
        "original_query": summary["original_query"],
        "original_query_vector": search.expansion.original_vector,
        "feedback_documents": [
            {"doc_id": d, "title": feedback_docs[d].title} for d in search.expansion.feedback_doc_ids
        ],
        "candidate_terms": [_candidate(c) for c in search.expansion.candidates],
        "expanded_terms": summary["expanded_terms"],
        "final_expanded_query": summary["final_expanded_query"],
        "expanded_query_vector": summary["expanded_query_vector"],
        "ranking_before": ranking_rows(conn, search.baseline, top_k),
        "ranking_after": ranking_rows(conn, search.ranking, top_k, baseline=search.baseline),
        "message": summary["message"],
    }


# ------------------------------------------------------------------ Rocchio
def _term_words(engine: SearchEngine, vector: dict[str, float]) -> list[dict]:
    return [{"term": t, "word": engine.index.display_form(t), "weight": w} for t, w in vector.items()]


def rocchio_summary(engine: SearchEngine, query: str, search: RocchioSearch, n: int = SUMMARY_TERMS) -> dict:
    result = search.rocchio
    positive = rocchio_math.top_terms(result.updated_vector, n)
    penalised = rocchio_math.top_terms(result.non_relevant_contribution, n)
    return {
        "original_query": query,
        "alpha": result.alpha,
        "beta": result.beta,
        "gamma": result.gamma,
        "normalized": result.normalized,
        "relevant_documents": result.relevant_ids,
        "non_relevant_documents": result.non_relevant_ids,
        "pseudo_feedback": search.pseudo_feedback,
        "top_positive_terms": _term_words(engine, dict(positive)),
        "top_negative_terms": [
            {
                "term": t,
                "word": engine.index.display_form(t),
                "penalty": w,
                "resulting_weight": result.updated_vector.get(t, 0.0),
            }
            for t, w in penalised
        ],
        "updated_query_terms": [engine.index.display_form(t) for t, _ in positive],
        "updated_query_vector": top_vector(result.updated_vector, n),
    }


def rocchio_workbench(
    engine: SearchEngine, conn: sqlite3.Connection, query: str, search: RocchioSearch, top_k: int, vector_terms: int
) -> dict:
    """Full step-by-step Rocchio view: preprocessing -> vectors -> formula terms -> similarity -> ranking."""
    result = search.rocchio
    analysis = engine.preprocessor.analyze(query)
    summary = rocchio_summary(engine, query, search, vector_terms)
    feedback_ids = result.relevant_ids + result.non_relevant_ids
    docs = repo.get_documents(conn, feedback_ids)

    ordered = sorted(result.terms, key=lambda t: (-max(abs(result.unclipped_vector.get(t, 0.0)), result.original_vector.get(t, 0.0)), t))
    calculations = [
        {
            "term": t,
            "word": engine.index.display_form(t),
            "original": result.original_vector.get(t, 0.0),
            "alpha_x_original": result.alpha * result.original_vector.get(t, 0.0),
            "relevant_contribution": result.relevant_contribution.get(t, 0.0),
            "non_relevant_contribution": result.non_relevant_contribution.get(t, 0.0),
            "before_clipping": result.unclipped_vector.get(t, 0.0),
            "updated": result.updated_vector.get(t, 0.0),
        }
        for t in ordered[:vector_terms]
    ]
    shown = search.ranking.ranked[:top_k]
    titles = repo.get_documents(conn, [s.doc_id for s in shown])
    return {
        "input": {
            "query": query,
            "relevant_doc_ids": result.relevant_ids,
            "non_relevant_doc_ids": result.non_relevant_ids,
            "pseudo_feedback": search.pseudo_feedback,
        },
        "formula": ROCCHIO_FORMULA,
        "parameters": {"alpha": result.alpha, "beta": result.beta, "gamma": result.gamma, "normalized": result.normalized},
        "preprocessing": {
            "normalized": analysis.normalized,
            "tokens": analysis.tokens,
            "stop_words_removed": analysis.stop_words_removed,
            "index_terms": analysis.index_terms,
            "unknown_terms": search.unknown_terms,
        },
        "feedback_documents": {
            "relevant": [{"doc_id": d, "title": docs[d].title} for d in result.relevant_ids],
            "non_relevant": [{"doc_id": d, "title": docs[d].title} for d in result.non_relevant_ids],
        },
        "original_query_vector": result.original_vector,
        "relevant_contribution": top_vector(result.relevant_contribution, vector_terms),
        "non_relevant_contribution": top_vector(result.non_relevant_contribution, vector_terms),
        "updated_query_vector": top_vector(result.updated_vector, vector_terms),
        "vector_sizes": {
            "original": len(result.original_vector),
            "relevant_contribution": len(result.relevant_contribution),
            "non_relevant_contribution": len(result.non_relevant_contribution),
            "updated": len(result.updated_vector),
        },
        "term_calculations": calculations,
        "clipped_terms": result.clipped_terms,
        "top_positive_terms": summary["top_positive_terms"],
        "top_negative_terms": summary["top_negative_terms"],
        "updated_query_terms": summary["updated_query_terms"],
        "similarity": [
            {
                "rank": i,
                "doc_id": s.doc_id,
                "title": titles[s.doc_id].title,
                "dot_product": s.dot,
                "query_norm": s.query_norm,
                "document_norm": s.doc_norm,
                "cosine": s.score,
            }
            for i, s in enumerate(shown, start=1)
        ],
        "ranking_before": ranking_rows(conn, search.baseline, top_k),
        "ranking": ranking_rows(conn, search.ranking, top_k, baseline=search.baseline),
    }
