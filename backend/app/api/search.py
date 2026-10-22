import sqlite3
import time

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_conn, get_engine, make_snippet
from app.core.errors import AppError
from app.database import repository as repo
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
            }
            if body.explain:
                item["explanation"] = {
                    "dot_product": s.dot,
                    "query_norm": s.query_norm,
                    "document_norm": s.doc_norm,
                    "term_contributions": s.term_contributions,
                }
            results.append(item)

        unknown = ranking.unknown_terms if ranking else []
        if not terms:
            message = "The query contains only stop words or punctuation, so there is nothing to search for."
        elif not ranked:
            message = "None of the query terms appear in the indexed documents." if len(unknown) == len(set(terms)) \
                else "No documents match the query."
        else:
            message = None
        response = {
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
        "results": [{"doc_id": d, "title": docs[d].title, "category": docs[d].category} for d in page_ids],
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
        "documents": [{"doc_id": d, "title": docs[d].title, "category": docs[d].category} for d in shown_ids],
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
