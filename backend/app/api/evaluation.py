"""Evaluation endpoints (precision / recall / F1 / P@K / R@K / AP / MAP)."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import asdict
from typing import Sequence

from fastapi import APIRouter, Depends

from app.api.deps import get_conn, get_engine
from app.core.errors import AppError
from app.database import evaluation as dataset
from app.database import repository as repo
from app.schemas.advanced import (
    EvaluationDatasetResponse,
    EvaluationMapRequest,
    EvaluationMapResponse,
    EvaluationRunRequest,
    EvaluationRunResponse,
    RetrievalOptionsIn,
)
from app.services import metrics
from app.services.advanced_retrieval import UnknownDocumentsError
from app.services.boolean_retrieval import BooleanQueryError
from app.services.evaluation import QueryEvaluation, RetrievalOptions, evaluate_query, format_map_calculation
from app.services.rocchio import RocchioError
from app.services.search_engine import SearchEngine

router = APIRouter(prefix="/evaluation", tags=["evaluation"])

MAP_FORMULA = "MAP = (1/Q) * sum over queries of AP(q);  AP = (sum of P@rank at each relevant document) / (total relevant)"


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def resolve_relevant(conn: sqlite3.Connection, query: str, ids: Sequence[int] | None) -> tuple[list[int], str]:
    """Relevant IDs from the request (validated against the database) or from the stored dataset."""
    if ids is None:
        judged = dataset.get_relevant_for_query(conn, query)
        if judged is None:
            raise AppError(
                400,
                "no_relevance_judgments",
                f"No relevance judgments are stored for {query!r}; pass relevant_doc_ids.",
            )
        return judged, "dataset"
    unique = list(dict.fromkeys(ids))
    if not unique:
        raise AppError(400, "no_relevance_judgments", "relevant_doc_ids must contain at least one document ID.")
    existing = repo.get_documents(conn, unique)
    missing = [i for i in unique if i not in existing]
    if missing:
        raise AppError(404, "document_not_found", f"Relevant documents do not exist: {missing}", {"missing": missing})
    return unique, "request"


def build_options(body: RetrievalOptionsIn) -> RetrievalOptions:
    return RetrievalOptions(
        mode=body.mode,
        top_k=body.top_k,
        feedback_relevant=getattr(body, "feedback_relevant_doc_ids", ()),
        feedback_non_relevant=getattr(body, "feedback_non_relevant_doc_ids", ()),
        pseudo_feedback_docs=body.pseudo_feedback_docs,
        alpha=body.alpha,
        beta=body.beta,
        gamma=body.gamma,
    )


def run_evaluation(engine: SearchEngine, query: str, relevant: Sequence[int], options: RetrievalOptions) -> QueryEvaluation:
    try:
        return evaluate_query(engine.advanced, query, relevant, options)
    except BooleanQueryError as exc:
        raise AppError(400, "invalid_boolean_query", exc.message, {"position": exc.position}) from exc
    except UnknownDocumentsError as exc:
        raise AppError(404, "document_not_found", str(exc), {"missing": exc.missing}) from exc
    except RocchioError as exc:
        raise AppError(400, "invalid_rocchio_input", str(exc)) from exc


def _metric_fields(ev: QueryEvaluation) -> dict:
    r = ev.result
    return {
        "precision": r.precision,
        "recall": r.recall,
        "f1": r.f1,
        "precision_at_k": r.precision_at_k,
        "recall_at_k": r.recall_at_k,
        "average_precision": r.average_precision,
        "relevant_doc_ids": r.relevant,
        "retrieved_doc_ids": r.retrieved_at_k,
        "relevant_retrieved_doc_ids": r.relevant_retrieved,
        "total_ranked": len(ev.ranked),
    }


@router.post("/run", response_model=EvaluationRunResponse)
def evaluate_one(
    body: EvaluationRunRequest,
    engine: SearchEngine = Depends(get_engine),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Evaluate one query: set metrics over the top-k results, AP over the whole ranking."""
    start = time.perf_counter()
    relevant, source = resolve_relevant(conn, body.query, body.relevant_doc_ids)
    with engine.lock:
        ev = run_evaluation(engine, body.query, relevant, build_options(body))
    return {
        "query": body.query,
        "mode": body.mode,
        "top_k": body.top_k,
        "relevance_source": source,
        **_metric_fields(ev),
        "took_ms": _ms(start),
    }


@router.post("/map", response_model=EvaluationMapResponse)
def evaluate_map(
    body: EvaluationMapRequest,
    engine: SearchEngine = Depends(get_engine),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Mean Average Precision over supplied judged queries (or the whole stored dataset)."""
    start = time.perf_counter()
    if body.queries is None:
        judged = [(q.query, q.relevant_doc_ids, "dataset") for q in dataset.list_queries(conn)]
        if not judged:
            raise AppError(
                404, "evaluation_dataset_empty", "No evaluation dataset is loaded. Run: python -m app.cli seed-evaluation"
            )
    else:
        judged = [(q.query, *resolve_relevant(conn, q.query, q.relevant_doc_ids)) for q in body.queries]
    options = build_options(body)
    per_query = []
    with engine.lock:
        for query, relevant, source in judged:
            ev = run_evaluation(engine, query, relevant, options)
            per_query.append(
                {
                    "query": query,
                    "relevance_source": source,
                    **_metric_fields(ev),
                    "ap_steps": [asdict(s) for s in ev.result.ap_steps],
                }
            )
    aps = [q["average_precision"] for q in per_query]
    return {
        "mode": body.mode,
        "top_k": body.top_k,
        "query_count": len(per_query),
        "mean_average_precision": metrics.mean_average_precision(aps),
        "mean_precision_at_k": metrics.mean_average_precision([q["precision_at_k"] for q in per_query]),
        "mean_recall_at_k": metrics.mean_average_precision([q["recall_at_k"] for q in per_query]),
        "map_calculation": format_map_calculation(aps),
        "formula": MAP_FORMULA,
        "per_query": per_query,
        "took_ms": _ms(start),
    }


@router.get("/dataset", response_model=EvaluationDatasetResponse)
def evaluation_dataset(conn: sqlite3.Connection = Depends(get_conn)):
    """The stored evaluation queries and their relevance judgments."""
    queries = dataset.list_queries(conn)
    return {
        "query_count": len(queries),
        "queries": [
            {"id": q.id, "query": q.query, "description": q.description, "relevant_doc_ids": q.relevant_doc_ids}
            for q in queries
        ],
    }


# ------------------------------------------------------------------ workbench view
def evaluation_workbench(engine: SearchEngine, conn: sqlite3.Connection, body: EvaluationRunRequest) -> dict:
    """Every intermediate number behind the metrics, for step-by-step display."""
    relevant, source = resolve_relevant(conn, body.query, body.relevant_doc_ids)
    with engine.lock:
        analysis = engine.preprocessor.analyze(body.query)
        ev = run_evaluation(engine, body.query, relevant, build_options(body))
    r = ev.result
    relevant_set = set(r.relevant)
    shown = r.retrieved_at_k
    docs = repo.get_documents(conn, shown)

    rows, hits = [], 0
    for rank, doc_id in enumerate(shown, start=1):
        hits += doc_id in relevant_set
        rows.append(
            {
                "rank": rank,
                "doc_id": doc_id,
                "title": docs[doc_id].title,
                "relevant": doc_id in relevant_set,
                "relevant_so_far": hits,
                "precision_at_rank": hits / rank,
                "recall_at_rank": hits / len(relevant_set),
            }
        )
    n_ret, n_rel, n_hit = len(shown), len(relevant_set), len(r.relevant_retrieved)
    ap_terms = " + ".join(f"{s.relevant_so_far}/{s.rank}" for s in r.ap_steps) or "0"
    return {
        "input": {"query": body.query, "mode": body.mode, "top_k": body.top_k, "relevance_source": source},
        "preprocessing": {
            "normalized": analysis.normalized,
            "tokens": analysis.tokens,
            "stop_words_removed": analysis.stop_words_removed,
            "index_terms": analysis.index_terms,
        },
        "retrieval": {"mode": body.mode, "total_ranked": len(ev.ranked)},
        "counts": {
            "retrieved": n_ret,
            "relevant_total": n_rel,
            "relevant_retrieved": n_hit,
            "k": body.top_k,
        },
        "relevant_doc_ids": r.relevant,
        "missed_relevant_doc_ids": sorted(relevant_set - set(r.relevant_retrieved)),
        "ranked_documents": rows,
        "metrics": {
            "precision": r.precision,
            "recall": r.recall,
            "f1": r.f1,
            "precision_at_k": r.precision_at_k,
            "recall_at_k": r.recall_at_k,
            "average_precision": r.average_precision,
        },
        "calculations": {
            "precision": f"relevant retrieved / retrieved = {n_hit} / {n_ret} = {r.precision:.4f}",
            "recall": f"relevant retrieved / total relevant = {n_hit} / {n_rel} = {r.recall:.4f}",
            "f1": f"2PR / (P + R) = 2 x {r.precision:.4f} x {r.recall:.4f} / ({r.precision:.4f} + {r.recall:.4f}) = {r.f1:.4f}",
            "precision_at_k": f"relevant in top {body.top_k} / {body.top_k} = {n_hit} / {body.top_k} = {r.precision_at_k:.4f}",
            "recall_at_k": f"relevant in top {body.top_k} / total relevant = {n_hit} / {n_rel} = {r.recall_at_k:.4f}",
            "average_precision": f"({ap_terms}) / {n_rel} = {r.average_precision:.4f}",
        },
        "average_precision_steps": [asdict(s) for s in r.ap_steps],
    }
