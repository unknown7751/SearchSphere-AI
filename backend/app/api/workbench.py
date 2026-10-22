"""Teaching/inspection endpoints that expose the intermediate IR computations."""
import sqlite3
import time
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.advanced_helpers import expansion_workbench, rocchio_workbench, run_rocchio
from app.api.deps import get_conn, get_engine
from app.api.evaluation import evaluation_workbench
from app.core.errors import AppError
from app.database import repository as repo
from app.schemas.advanced import (
    EvaluationRunRequest,
    QueryExpansionRequest,
    RelevanceFeedbackRequest,
    RocchioRequest,
)
from app.schemas.workbench import (
    CosineRequest,
    CosineResponse,
    IncidenceMatrixRequest,
    IncidenceMatrixResponse,
    InvertedIndexListResponse,
    InvertedIndexTermResponse,
    PreprocessRequest,
    PreprocessResponse,
    TfidfRequest,
    TfidfResponse,
)
from app.services.boolean_retrieval import incidence_matrix, intersect
from app.services.search_engine import SearchEngine

router = APIRouter(prefix="/workbench", tags=["workbench"])

TFIDF_FORMULAS = {
    "tf": "tf(t,d) = raw count of t in d",
    "df": "df(t) = number of indexed documents containing t",
    "idf": "idf(t) = ln((N + 1) / (df(t) + 1)) + 1",
    "tfidf": "tfidf(t,d) = tf(t,d) * idf(t)",
}


def _require_indexed(engine: SearchEngine, ids: list[int]) -> list[int]:
    ids = list(dict.fromkeys(ids))
    missing = [i for i in ids if not engine.index.has_document(i)]
    if missing:
        raise AppError(404, "document_not_found", f"Documents not found in the index: {missing}", {"missing": missing})
    return ids


@router.post("/preprocess", response_model=PreprocessResponse)
def preprocess(body: PreprocessRequest, engine: SearchEngine = Depends(get_engine)):
    result = engine.preprocessor.analyze(body.text)
    return {
        "original": result.original,
        "normalized": result.normalized,
        "tokens": result.tokens,
        "stop_words_removed": result.stop_words_removed,
        "tokens_without_stopwords": result.tokens_without_stopwords,
        "stemmed_tokens": result.stemmed_tokens,
        "lemmatized_tokens": result.lemmatized_tokens,
        "index_terms": result.index_terms,
        "index_form": engine.preprocessor.config.index_form,
    }


@router.post("/incidence-matrix", response_model=IncidenceMatrixResponse)
def incidence(
    body: IncidenceMatrixRequest,
    engine: SearchEngine = Depends(get_engine),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Binary term-document incidence matrix for chosen terms and a subset of documents."""
    with engine.lock:
        ids = _require_indexed(engine, body.document_ids) if body.document_ids else engine.index.all_doc_ids()[:20]
        docs = repo.get_documents(conn, ids)
        rows, ignored = [], []
        for raw in dict.fromkeys(body.terms):
            terms = engine.preprocessor.index_terms(raw)
            if not terms:
                ignored.append(raw)
                continue
            per_term = incidence_matrix(engine.index, terms, ids)
            row = [int(all(col)) for col in zip(*per_term)]
            df_ids = engine.index.doc_ids(terms[0])
            for t in terms[1:]:
                df_ids = intersect(df_ids, engine.index.doc_ids(t))
            rows.append({"term": raw, "index_terms": terms, "document_frequency": len(df_ids), "row": row})
        return {
            "documents": [{"doc_id": i, "title": docs[i].title} for i in ids],
            "rows": rows,
            "ignored_terms": ignored,
        }


@router.get("/inverted-index", response_model=InvertedIndexTermResponse | InvertedIndexListResponse)
def inverted_index(
    term: str | None = Query(None, max_length=100, description="Look up one word's postings list"),
    prefix: str | None = Query(None, max_length=100, description="Filter the vocabulary listing by index-term prefix"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    engine: SearchEngine = Depends(get_engine),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Inspect the inverted index: one term's postings, or the alphabetical vocabulary."""
    with engine.lock:
        stats = engine.index.stats()
        if term is not None:
            terms = engine.preprocessor.index_terms(term)
            if len(terms) != 1:
                raise AppError(400, "invalid_term", "Provide exactly one word that is not a stop word.")
            info = engine.index.inspect(terms[0])
            docs = repo.get_documents(conn, [p["doc_id"] for p in info["postings"]])
            return InvertedIndexTermResponse(
                query=term,
                term=terms[0],
                document_frequency=info["document_frequency"],
                postings=[{**p, "title": docs[p["doc_id"]].title} for p in info["postings"]],
                stats=stats,
            )
        vocab = engine.index.vocabulary()
        if prefix:
            p = prefix.lower().strip()
            vocab = [t for t in vocab if t.startswith(p)]
        offset = (page - 1) * page_size
        return InvertedIndexListResponse(
            prefix=prefix,
            terms=[{"term": t, "document_frequency": engine.index.df(t)} for t in vocab[offset : offset + page_size]],
            total_terms=len(vocab),
            page=page,
            page_size=page_size,
            stats=stats,
        )


@router.post("/tfidf", response_model=TfidfResponse)
def tfidf(body: TfidfRequest, engine: SearchEngine = Depends(get_engine), conn: sqlite3.Connection = Depends(get_conn)):
    """TF, DF, IDF and TF-IDF for chosen documents (and optional query terms)."""
    with engine.lock:
        ids = _require_indexed(engine, body.document_ids)
        docs = repo.get_documents(conn, ids)
        model = engine.model
        q_terms: list[str] = engine.preprocessor.index_terms(body.query) if body.query else []
        q_counts = Counter(q_terms)
        known = sorted(t for t in q_counts if model.df(t) > 0)
        unknown = sorted(t for t in q_counts if model.df(t) == 0)
        query_rows = None
        if body.query is not None:
            query_rows = [
                {"term": t, "tf": q_counts[t], "df": model.df(t), "idf": model.idf(t), "tfidf": q_counts[t] * model.idf(t)}
                for t in known
            ]
        out_docs = []
        for i in ids:
            out_docs.append(
                {
                    "doc_id": i,
                    "title": docs[i].title,
                    "vector_size": len(model.document_vector(i)),
                    "top_terms": model.top_terms(i, body.top_n),
                    "query_term_weights": [
                        {"term": t, "tf": model.tf(t, i), "df": model.df(t), "idf": model.idf(t), "tfidf": model.tfidf(t, i)}
                        for t in known
                    ],
                }
            )
        return {
            "num_documents": model.num_docs,
            "formulas": TFIDF_FORMULAS,
            "query_terms": query_rows,
            "unknown_terms": unknown,
            "documents": out_docs,
        }


@router.post("/cosine", response_model=CosineResponse)
def cosine(body: CosineRequest, engine: SearchEngine = Depends(get_engine), conn: sqlite3.Connection = Depends(get_conn)):
    """Cosine similarity breakdown (dot product, norms, score) for ranked or chosen documents."""
    start = time.perf_counter()
    with engine.lock:
        terms = engine.preprocessor.index_terms(body.query)
        ids = _require_indexed(engine, body.document_ids) if body.document_ids else None
        ranking = engine.ranker.rank(terms, candidate_ids=ids)
        scored = ranking.ranked if ids is not None else ranking.ranked[: body.top_k]
        docs = repo.get_documents(conn, [s.doc_id for s in scored])
        out = []
        for rank, s in enumerate(scored, start=1):
            dvec = engine.model.document_vector(s.doc_id)
            out.append(
                {
                    "rank": rank,
                    "doc_id": s.doc_id,
                    "title": docs[s.doc_id].title,
                    "dot_product": s.dot,
                    "query_norm": s.query_norm,
                    "document_norm": s.doc_norm,
                    "cosine": s.score,
                    "term_contributions": s.term_contributions,
                    "document_vector_shared_terms": {t: dvec[t] for t in ranking.query_vector if t in dvec},
                }
            )
        response = {
            "query_terms": terms,
            "query_vector": ranking.query_vector,
            "unknown_terms": ranking.unknown_terms,
            "formula": "cosine(q,d) = dot(q,d) / (||q|| * ||d||)",
            "documents": out,
        }
    response["took_ms"] = round((time.perf_counter() - start) * 1000, 3)
    return response


# ------------------------------------------------------------------ Phase 2: advanced IR + evaluation
@router.post("/query-expansion", response_model=dict[str, Any])
def query_expansion(
    body: QueryExpansionRequest, engine: SearchEngine = Depends(get_engine), conn: sqlite3.Connection = Depends(get_conn)
):
    """Original query -> expanded terms -> final expanded query, with the ranking before and after."""
    start = time.perf_counter()
    with engine.lock:
        search = engine.advanced.expanded_search(
            body.query,
            feedback_docs=body.feedback_docs,
            max_terms=body.max_expansion_terms,
            expansion_weight=body.expansion_weight,
        )
        response = expansion_workbench(engine, conn, body.query, search, body.top_k)
    response["took_ms"] = round((time.perf_counter() - start) * 1000, 3)
    return response


@router.post("/rocchio", response_model=dict[str, Any])
def rocchio(body: RocchioRequest, engine: SearchEngine = Depends(get_engine), conn: sqlite3.Connection = Depends(get_conn)):
    """Rocchio step by step: vectors, per-term arithmetic, cosine similarity and the new ranking."""
    start = time.perf_counter()
    with engine.lock:
        search = run_rocchio(engine, body.query, body)
        response = rocchio_workbench(engine, conn, body.query, search, body.top_k, body.vector_terms)
    response["took_ms"] = round((time.perf_counter() - start) * 1000, 3)
    return response


@router.post("/relevance-feedback", response_model=dict[str, Any])
def relevance_feedback(
    body: RelevanceFeedbackRequest, engine: SearchEngine = Depends(get_engine), conn: sqlite3.Connection = Depends(get_conn)
):
    """User-judged relevance feedback: vector breakdown plus how the judgments re-ranked the results."""
    if not body.relevant_doc_ids and not body.non_relevant_doc_ids and not body.pseudo_feedback_docs:
        raise AppError(
            400, "no_feedback_documents", "Provide relevant_doc_ids, non_relevant_doc_ids or pseudo_feedback_docs."
        )
    start = time.perf_counter()
    with engine.lock:
        search = run_rocchio(engine, body.query, body)
        full = rocchio_workbench(engine, conn, body.query, search, body.top_k, body.vector_terms)
    keep = (
        "input", "parameters", "preprocessing", "feedback_documents", "original_query_vector", "relevant_contribution",
        "non_relevant_contribution", "updated_query_vector", "term_calculations", "top_positive_terms",
        "top_negative_terms", "updated_query_terms", "ranking_before",
    )
    response = {k: full[k] for k in keep}
    response["ranking_after"] = full["ranking"]
    response["took_ms"] = round((time.perf_counter() - start) * 1000, 3)
    return response


@router.post("/evaluation", response_model=dict[str, Any])
def evaluation(
    body: EvaluationRunRequest, engine: SearchEngine = Depends(get_engine), conn: sqlite3.Connection = Depends(get_conn)
):
    """Evaluation with every intermediate count, per-rank precision/recall and the AP arithmetic."""
    start = time.perf_counter()
    response = evaluation_workbench(engine, conn, body)
    response["took_ms"] = round((time.perf_counter() - start) * 1000, 3)
    return response
