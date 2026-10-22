import sqlite3
import time

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_conn, get_engine, make_snippet
from app.core.errors import AppError
from app.database import repository as repo
from app.api.advanced_helpers import expansion_summary, rocchio_summary, run_rocchio
from app.schemas.advanced import (
    ExpandedSearchRequest,
    ExpandedSearchResponse,
    RocchioSearchRequest,
    RocchioSearchResponse,
)
from app.schemas.search import (
    BooleanSearchRequest,
    BooleanSearchResponse,
    SearchRequest,
    SearchResponse,
    SuggestionsResponse,
    TolerantSearchRequest,
    TolerantSearchResponse,
)
from app.services.boolean_retrieval import BooleanQueryError
from app.services.search_engine import SearchEngine
from app.services.tolerant_retrieval import PatternError

router = APIRouter(prefix="/search", tags=["search"])


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def _explanation(engine: SearchEngine, ranking, scored) -> dict:
    """Score breakdown for one result: dot product, norms and the per-term TF-IDF evidence."""
    model = engine.model
    dvec = model.document_vector(scored.doc_id)
    matching = [
        {
            "term": t,
            "word": engine.index.display_form(t),
            "tf": model.tf(t, scored.doc_id),
            "df": model.df(t),
            "idf": model.idf(t),
            "tfidf": dvec[t],
            "query_weight": ranking.query_vector[t],
            "contribution": scored.term_contributions[t],
        }
        for t in sorted(scored.term_contributions, key=lambda t: (-scored.term_contributions[t], t))
    ]
    return {
        "dot_product": scored.dot,
        "query_norm": scored.query_norm,
        "document_norm": scored.doc_norm,
        "term_contributions": scored.term_contributions,
        "matching_terms": matching,
    }


def render_ranked_search(engine: SearchEngine, conn: sqlite3.Connection, body: SearchRequest, analysis, ranking) -> dict:
    """Filter, paginate and describe a ranking (shared by TF-IDF, expanded and Rocchio search).

    Must be called while holding ``engine.lock``. ``took_ms`` is added by the caller.
    """
    terms = analysis.index_terms
    ranked = ranking.ranked if ranking else []
    if body.category and ranked:
        docs = repo.get_documents(conn, [s.doc_id for s in ranked])
        ranked = [s for s in ranked if docs[s.doc_id].category == body.category]
    total = len(ranked)
    offset = (body.page - 1) * body.page_size
    page_items = ranked[offset : offset + body.page_size]
    docs = repo.get_documents(conn, [s.doc_id for s in page_items])

    results = []
    for i, s in enumerate(page_items, start=offset + 1):
        doc = docs[s.doc_id]
        item = {
            "rank": i,
            "doc_id": doc.id,
            "title": doc.title,
            "category": doc.category,
            "snippet": make_snippet(doc.text),
            "score": s.score,
            "source_type": doc.source_type,
            "source_url": doc.source_url,
        }
        if body.explain:
            item["explanation"] = _explanation(engine, ranking, s)
        results.append(item)

    unknown = ranking.unknown_terms if ranking else []
    if not terms and not ranked:
        message = "The query contains only stop words or punctuation, so there is nothing to search for."
    elif not ranked:
        message = "None of the query terms appear in the indexed documents." if len(unknown) == len(set(terms))             else "No documents match the query."
    else:
        message = None
    return {
        "query": {
            "original": body.query,
            "normalized": analysis.normalized,
            "tokens": analysis.tokens,
            "stop_words_removed": analysis.stop_words_removed,
            "index_terms": terms,
            "unknown_terms": unknown,
        },
        "query_vector": ranking.query_vector if ranking else {},
        "results": results,
        "total_results": total,
        "page": body.page,
        "page_size": body.page_size,
        "message": message,
    }


@router.post("", response_model=SearchResponse)
def ranked_search(
    body: SearchRequest,
    engine: SearchEngine = Depends(get_engine),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """TF-IDF / cosine-similarity ranked retrieval."""
    start = time.perf_counter()
    with engine.lock:
        analysis = engine.preprocessor.analyze(body.query)
        terms = analysis.index_terms
        ranking = engine.ranker.rank(terms) if terms else None
        response = render_ranked_search(engine, conn, body, analysis, ranking)
    response["took_ms"] = _ms(start)
    return response


@router.post("/expanded", response_model=ExpandedSearchResponse)
def expanded_search(
    body: ExpandedSearchRequest,
    engine: SearchEngine = Depends(get_engine),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """TF-IDF search with corpus-driven query expansion (the expanded vector is what is ranked)."""
    start = time.perf_counter()
    with engine.lock:
        analysis = engine.preprocessor.analyze(body.query)
        search = engine.advanced.expanded_search(
            body.query,
            feedback_docs=body.feedback_docs,
            max_terms=body.max_expansion_terms,
            expansion_weight=body.expansion_weight,
        )
        response = render_ranked_search(engine, conn, body, analysis, search.ranking if analysis.index_terms else None)
        response["expansion"] = expansion_summary(body.query, search.expansion)
    response["took_ms"] = _ms(start)
    return response


@router.post("/rocchio", response_model=RocchioSearchResponse)
def rocchio_search(
    body: RocchioSearchRequest,
    engine: SearchEngine = Depends(get_engine),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Ranked retrieval with a Rocchio-modified query vector built from relevance feedback."""
    start = time.perf_counter()
    with engine.lock:
        analysis = engine.preprocessor.analyze(body.query)
        search = run_rocchio(engine, body.query, body)
        response = render_ranked_search(engine, conn, body, analysis, search.ranking)
        response["rocchio"] = rocchio_summary(engine, body.query, search)
    response["took_ms"] = _ms(start)
    return response


@router.post("/boolean", response_model=BooleanSearchResponse)
def boolean_search(
    body: BooleanSearchRequest,
    engine: SearchEngine = Depends(get_engine),
    conn: sqlite3.Connection = Depends(get_conn),
):
    start = time.perf_counter()
    with engine.lock:
        try:
            result = engine.boolean.search(body.query)
        except BooleanQueryError as exc:
            raise AppError(400, "invalid_boolean_query", exc.message, {"position": exc.position}) from exc
        offset = (body.page - 1) * body.page_size
        page_ids = result.doc_ids[offset : offset + body.page_size]
        docs = repo.get_documents(conn, page_ids)
    return {
        "query": body.query,
        "parsed_expression": result.parsed_expression,
        "ast": result.ast,
        "index_terms": result.index_terms,
        "unknown_terms": result.unknown_terms,
        "matching_doc_ids": result.doc_ids,
        "results": [{"doc_id": d, "title": docs[d].title, "category": docs[d].category, "source_type": docs[d].source_type, "source_url": docs[d].source_url} for d in page_ids],
        "total_results": len(result.doc_ids),
        "page": body.page,
        "page_size": body.page_size,
        "steps": [vars(s) for s in result.steps],
        "took_ms": _ms(start),
    }


@router.post("/tolerant", response_model=TolerantSearchResponse)
def tolerant_search(
    body: TolerantSearchRequest,
    engine: SearchEngine = Depends(get_engine),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Prefix (``mach*``) and wildcard (``comput*r``) dictionary lookup."""
    start = time.perf_counter()
    with engine.lock:
        try:
            result = engine.tolerant.search(body.pattern, body.max_expansions)
        except PatternError as exc:
            raise AppError(400, "invalid_pattern", str(exc)) from exc
        shown_ids = result.doc_ids[:100] if body.include_documents else []
        docs = repo.get_documents(conn, shown_ids)
    message = None
    if result.total_matches == 0:
        message = f"No dictionary term matches '{result.pattern}'."
    elif result.truncated:
        message = (
            f"{result.total_matches} terms matched; only the {len(result.matched_terms)} most frequent "
            "were expanded (expansion limit)."
        )
    return {
        "pattern": result.pattern,
        "kind": result.kind,
        "strategy": result.strategy,
        "matched_term_count": len(result.matched_terms),
        "total_matches": result.total_matches,
        "expansion_limit": body.max_expansions or engine.tolerant.default_limit,
        "truncated": result.truncated,
        "matched_terms": [
            {"term": m.term, "index_term": m.index_term, "document_count": len(m.doc_ids), "doc_ids": m.doc_ids}
            for m in result.matched_terms
        ],
        "documents": [{"doc_id": d, "title": docs[d].title, "category": docs[d].category, "source_type": docs[d].source_type, "source_url": docs[d].source_url} for d in shown_ids],
        "total_documents": len(result.doc_ids),
        "took_ms": _ms(start),
        "message": message,
    }


@router.get("/suggestions", response_model=SuggestionsResponse)
def suggestions(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(8, ge=1, le=20),
    engine: SearchEngine = Depends(get_engine),
):
    """Autocomplete the last word of ``q`` from the dictionary, most frequent first."""
    with engine.lock:
        found = engine.tolerant.suggest(q, limit)
    return {"prefix": q, "suggestions": [{"term": t, "document_count": n} for t, n in found]}
